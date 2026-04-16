#!/usr/bin/env python3
"""
Run Python code in a live Isaac Sim (via the Claude Bridge, isaac_bridge.py).

Usage:
    isaac_run.py 'print(stage.GetRootLayer().identifier)'   # one-liner argument
    isaac_run.py <<'EOF'                                     # multi-line heredoc
    timeline.play()
    await frames(60)
    EOF
    isaac_run.py < script.py                                 # from a file

If the bridge isn't running but Isaac Sim's own Python server extension is
(isaacsim.code_editor.python_server, port 8226), the bridge is started through it.

Env: ISAAC_BRIDGE_HOST (127.0.0.1), ISAAC_BRIDGE_PORT (8723), ISAAC_RUN_TIMEOUT (60s, 0 = none),
     ISAAC_PYTHON_SERVER_PORT (8226, 0 = never bootstrap).
"""

import json
import os
import socket
import sys
import time

HOST = os.environ.get("ISAAC_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ISAAC_BRIDGE_PORT", "8723"))
BOOT_PORT = int(os.environ.get("ISAAC_PYTHON_SERVER_PORT", "8226"))
BRIDGE_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isaac_bridge.py")
try:
    TIMEOUT = float(os.environ.get("ISAAC_RUN_TIMEOUT", "60"))
except ValueError:
    TIMEOUT = 60.0

START_HINT = ("Start it inside Isaac Sim: launch with `isaac-sim.sh --exec ~/.claude/skills/isaacsim/isaac_bridge.py`,"
              " or run exec(open('<path>/isaac_bridge.py').read()) in Window > Script Editor.")


def _recv_all(s):
    chunks = []
    while True:
        chunk = s.recv(1 << 16)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def bootstrap():
    """Start the bridge through Isaac Sim's built-in Python server, if that is enabled.
    The bridge source is sent inline, so this also works for Docker / remote hosts."""
    if BOOT_PORT <= 0:
        return False
    with open(BRIDGE_PY, encoding="utf-8") as f:
        src = f.read()
    code = f"exec(compile({src!r}, 'isaac_bridge.py', 'exec'), {{'__name__': '__main__'}})"
    try:
        with socket.create_connection((HOST, BOOT_PORT), timeout=3) as s:
            s.sendall(code.encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
            s.settimeout(30)
            resp = json.loads(_recv_all(s).decode("utf-8"))
    except (OSError, ValueError):
        return False
    return resp.get("status") == "ok"


def connect():
    try:
        return socket.create_connection((HOST, PORT), timeout=5)
    except OSError as e:
        err = e
    if bootstrap():
        for _ in range(50):
            try:
                return socket.create_connection((HOST, PORT), timeout=5)
            except OSError as e:
                err = e
                time.sleep(0.1)
    sys.exit(f"ERROR: no Isaac Sim bridge at {HOST}:{PORT} ({err}). Isaac Sim still loading, or bridge not started. "
             + START_HINT)


def main():
    if len(sys.argv) > 2 or sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 2 else 2)
    code = sys.argv[1] if len(sys.argv) == 2 else sys.stdin.read()
    if not code.strip():
        sys.exit("error: no code given (pass as argument or via stdin/heredoc)")

    s = connect()
    with s:
        s.sendall(json.dumps({"code": code, "timeout": TIMEOUT}).encode("utf-8"))
        s.shutdown(socket.SHUT_WR)
        # the bridge cancels async scripts at TIMEOUT; the margin covers a busy/frozen main thread
        s.settimeout(TIMEOUT + 15 if TIMEOUT > 0 else None)
        try:
            data = _recv_all(s)
        except socket.timeout:
            sys.exit(f"ERROR: Timeout - no reply after {TIMEOUT + 15:g}s. Isaac Sim's main thread is busy or frozen"
                     " (a long synchronous loop?). Set ISAAC_RUN_TIMEOUT for long operations.")
    if not data:
        sys.exit("ERROR: bridge closed the connection without a reply (Isaac Sim shutting down?)")
    resp = json.loads(data.decode("utf-8"))
    out = resp.get("output", "")
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    sys.exit(0 if resp.get("ok") else 1)


if __name__ == "__main__":
    main()
