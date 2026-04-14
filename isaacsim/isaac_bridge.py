"""
Claude Bridge for Isaac Sim - runs Python sent by isaac_run.py inside Isaac Sim.

Listens on 127.0.0.1:8723 (env ISAAC_BRIDGE_HOST / ISAAC_BRIDGE_PORT) and runs each
request on Kit's main thread between frames. Scripts may use top-level `await`.

Start it any one way:
    isaac-sim.sh --exec /path/to/isaac_bridge.py                 # at launch
    exec(open("/path/to/isaac_bridge.py").read())                # Window > Script Editor

Re-running it restarts the bridge. Protocol: the client sends one JSON object
{"code": str, "timeout": seconds} and closes its write side; the bridge replies
{"ok": bool, "output": str} and closes.
"""

import ast
import asyncio
import contextvars
import inspect
import io
import json
import linecache
import os
import socket
import sys
import tempfile
import time
import traceback

HOST = os.environ.get("ISAAC_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ISAAC_BRIDGE_PORT", "8723"))
SCRIPT = "<isaac_run>"
STALE_SECONDS = 60  # drop connections that never finish sending

# exposed to scripts as `shared`; kept on `sys` so it survives runs and bridge restarts
SHARED = getattr(sys, "_isaac_bridge_shared", None)
if SHARED is None:
    SHARED = sys._isaac_bridge_shared = {}
_OUT = contextvars.ContextVar("isaac_bridge_out", default=None)  # per-request output buffer


# --- output capture -----------------------------------------------------------------

class _Router:
    """sys.stdout/stderr stand-in: writes go to the current request's buffer (a context
    variable, so it follows the request's asyncio task across frames), else pass through."""

    _isaac_bridge_router = True

    def __init__(self, fallback):
        self.fallback = fallback

    def write(self, s):
        buf = _OUT.get()
        if buf is None:
            return self.fallback.write(s)
        buf.write(s)
        return len(s)

    def flush(self):
        if _OUT.get() is None:
            self.fallback.flush()

    def __getattr__(self, name):
        return getattr(self.fallback, name)


def _install_router():
    # Re-checked per request: Kit / the Script Editor may swap sys.stdout at any time.
    for name in ("stdout", "stderr"):
        cur = getattr(sys, name)
        if isinstance(cur, _Router):
            continue
        base = cur.fallback if getattr(cur, "_isaac_bridge_router", False) else cur  # a previous bridge's router
        setattr(sys, name, _Router(base))


# --- helpers exposed to scripts ------------------------------------------------------

async def frames(n=1):
    """Let n app updates (rendered frames / physics steps while playing) pass."""
    import omni.kit.app

    app = omni.kit.app.get_app()
    for _ in range(int(n)):
        await app.next_update_async()


async def screenshot(path=None, settle=3):
    """Capture the active viewport to a PNG and return its path."""
    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport

    vp = get_active_viewport()
    if vp is None:
        raise RuntimeError("no active viewport (headless?) - render a camera with omni.replicator.core instead")
    path = os.path.abspath(path or os.path.join(tempfile.gettempdir(), "isaac_view.png"))
    if os.path.exists(path):
        os.remove(path)
    await frames(settle)  # let the renderer catch up with recent edits
    cap = capture_viewport_to_file(vp, path)
    waiter = getattr(cap, "wait_for_result", None)
    if waiter is not None:
        res = waiter()
        if inspect.isawaitable(res):
            await res
    for _ in range(300):
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            return path
        await frames(1)
    raise RuntimeError(f"viewport capture produced no file at {path}")


def set_view(eye, target, camera="/OmniverseKit_Persp"):
    """Point a camera (default: the viewport's perspective camera) from eye at target, in stage units."""
    from pxr import Gf, Usd, UsdGeom

    eye, target = Gf.Vec3d(*eye), Gf.Vec3d(*target)
    try:
        from omni.kit.viewport.utility import get_active_viewport
        from omni.kit.viewport.utility.camera_state import ViewportCameraState

        state = ViewportCameraState(camera, get_active_viewport())
        state.set_position_world(eye, True)
        state.set_target_world(target, True)
        return
    except ImportError:
        pass
    import omni.usd  # fallback: write a look-at transform into the session layer (not saved with the scene)

    stage = omni.usd.get_context().get_stage()
    up = Gf.Vec3d(0, 0, 1) if UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z else Gf.Vec3d(0, 1, 0)
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        xf = UsdGeom.Xformable(stage.GetPrimAtPath(camera))
        xf.ClearXformOpOrder()
        xf.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, target, up).GetInverse())


def _namespace():
    ns = {"__name__": "__isaac_run__", "shared": SHARED, "frames": frames, "screenshot": screenshot,
          "set_view": set_view}
    try:
        import carb
        import omni.kit.app
        import omni.timeline
        import omni.usd

        ctx = omni.usd.get_context()
        ns.update(omni=omni, carb=carb, app=omni.kit.app.get_app(), ctx=ctx, stage=ctx.get_stage(),
                  timeline=omni.timeline.get_timeline_interface())
    except ImportError:
        pass
    try:
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, Vt

        ns.update(Usd=Usd, UsdGeom=UsdGeom, UsdPhysics=UsdPhysics, UsdShade=UsdShade, UsdLux=UsdLux,
                  Sdf=Sdf, Gf=Gf, Vt=Vt)
    except ImportError:
        pass
    try:
        import numpy as np

        ns["np"] = np
    except ImportError:
        pass
    return ns


# --- running a request ---------------------------------------------------------------

def _format_error(e):
    frames_ = traceback.extract_tb(e.__traceback__)
    mine = [f for f in frames_ if f.filename == SCRIPT]
    out = "".join(traceback.format_exception_only(type(e), e))
    if mine:
        out = "Traceback (most recent call last):\n" + "".join(traceback.format_list(mine)) + out
    if mine and frames_[-1].filename != SCRIPT:  # where inside omni/isaacsim it was raised
        f = frames_[-1]
        out += f"  (raised in {f.filename}:{f.lineno} in {f.name})\n"
    return out


class _Timeout(Exception):
    pass


async def _execute(code, timeout):
    buf = io.StringIO()
    token = _OUT.set(buf)
    ok = False
    try:
        _install_router()
        linecache.cache[SCRIPT] = (len(code), None, code.splitlines(True), SCRIPT)
        compiled = compile(code, SCRIPT, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        result = eval(compiled, _namespace())  # a coroutine if the code used top-level await
        if inspect.iscoroutine(result):
            task = asyncio.ensure_future(result)  # inherits this context -> output still captured
            done, _ = await asyncio.wait({task}, timeout=timeout if timeout and timeout > 0 else None)
            if not done:
                task.cancel()
                raise _Timeout()
            task.result()  # re-raise the script's own exception, if any
        ok = True
    except _Timeout:
        buf.write(f"ERROR: script still running after {timeout:g}s - cancelled (ISAAC_RUN_TIMEOUT to raise)\n")
    except SystemExit as e:
        ok = e.code in (None, 0)
    except BaseException as e:  # never let a script take the bridge (or Kit) down
        buf.write(_format_error(e))
    finally:
        _OUT.reset(token)
    return ok, buf.getvalue()


class Bridge:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":  # on Windows SO_REUSEADDR would allow port hijacking
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(16)
        self.sock.setblocking(False)
        self.pending = {}  # conn -> (bytearray, t_accepted)
        self.running = True
        self.task = asyncio.ensure_future(self._loop())

    async def _loop(self):
        import omni.kit.app

        app = omni.kit.app.get_app()
        while self.running:
            await app.next_update_async()  # poll once per frame, on the main thread
            try:
                self._poll()
            except Exception as e:  # keep serving no matter what
                print(f"[isaac_bridge] poll error: {e}")

    def _poll(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                break
            conn.setblocking(False)
            self.pending[conn] = (bytearray(), time.time())
        for conn, (buf, t0) in list(self.pending.items()):
            try:
                while True:
                    chunk = conn.recv(1 << 16)
                    if not chunk:  # client finished sending
                        del self.pending[conn]
                        asyncio.ensure_future(self._handle(conn, bytes(buf)))
                        break
                    buf += chunk
            except (BlockingIOError, InterruptedError):
                if time.time() - t0 > STALE_SECONDS:
                    self._drop(conn)
            except OSError:
                self._drop(conn)

    def _drop(self, conn):
        self.pending.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass

    async def _handle(self, conn, raw):
        try:
            req = json.loads(raw.decode("utf-8"))
            ok, out = await _execute(req["code"], float(req.get("timeout") or 0))
        except Exception as e:
            ok, out = False, f"ERROR: bad request: {e}\n"
        try:
            conn.setblocking(True)
            conn.settimeout(10)
            conn.sendall(json.dumps({"ok": ok, "output": out}).encode("utf-8"))
        except OSError:
            pass  # client gave up
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        self.running = False
        self.task.cancel()
        for conn in list(self.pending):
            self._drop(conn)
        try:
            self.sock.close()
        except OSError:
            pass


def start(host=None, port=None):
    """(Re)start the bridge; the instance is kept on `sys` so a re-run can stop the old one."""
    stop()
    host, port = host or HOST, port or PORT
    try:
        bridge = Bridge(host, port)
    except OSError as e:
        print(f"[isaac_bridge] could not listen on {host}:{port}: {e} (another Isaac Sim running?"
              " set ISAAC_BRIDGE_PORT)")
        return None
    sys._isaac_bridge = bridge
    print(f"[isaac_bridge] listening on {host}:{port}")
    return bridge


def stop():
    old = getattr(sys, "_isaac_bridge", None)
    if old is not None:
        try:
            old.stop()
        except Exception:
            pass
        sys._isaac_bridge = None


start()
