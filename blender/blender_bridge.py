"""
Claude Bridge - Minimal Blender addon for external code execution.
Watches the bridge dir for cmd-<id>.py files and writes result-<id>.txt.
Per-request ids correlate responses; writes are atomic (temp + rename).
"""

bl_info = {
    "name": "Claude Bridge",
    "author": "Claude",
    "version": (2, 0),
    "blender": (3, 0, 0),
    "location": "Runs in background",
    "description": "Execute Python code from external scripts",
    "category": "Development",
}

import bpy
import io
import os
import sys
import tempfile
import time
import traceback

BRIDGE_DIR = os.path.join(tempfile.gettempdir(), "blender_claude_bridge")
STALE_SECONDS = 60  # GC unclaimed commands/results older than this


def execute_command():
    """Poll for cmd-<id>.py files, exec each, write result-<id>.txt."""
    try:
        for fname in sorted(os.listdir(BRIDGE_DIR)):
            path = os.path.join(BRIDGE_DIR, fname)
            stale = time.time() - os.path.getmtime(path) > STALE_SECONDS
            if fname.startswith("result-") and fname.endswith(".txt"):
                if stale:  # client gave up; nobody will read it
                    os.remove(path)
                continue
            if not (fname.startswith("cmd-") and fname.endswith(".py")):
                continue
            if stale:  # e.g. sent while Blender was closed; don't run it late
                os.remove(path)
                continue

            with open(path) as f:
                code = f.read()
            os.remove(path)
            req_id = fname[len("cmd-"):-len(".py")]

            buf = io.StringIO()
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = buf
            try:
                exec(code, {"bpy": bpy, "__builtins__": __builtins__})
                status = "OK"
            except BaseException as e:  # SystemExit too — must never kill the timer
                buf.write(f"ERROR: {e}\n{traceback.format_exc()}")
                status = "ERROR"
            finally:
                sys.stdout, sys.stderr = old_out, old_err

            tmp = os.path.join(BRIDGE_DIR, f".result-{req_id}.tmp")
            with open(tmp, "w") as f:
                f.write(f"{status}\n{buf.getvalue()}")
            os.replace(tmp, os.path.join(BRIDGE_DIR, f"result-{req_id}.txt"))
    except Exception as e:
        print(f"Claude Bridge error: {e}")
    return 0.1  # always reschedule; a raising callback would unregister the timer


class ClaudeBridgeOperator(bpy.types.Operator):
    """Start the Claude Bridge listener"""
    bl_idname = "claude.bridge_start"
    bl_label = "Start Claude Bridge"

    def execute(self, context):
        os.makedirs(BRIDGE_DIR, exist_ok=True)
        if not bpy.app.timers.is_registered(execute_command):
            bpy.app.timers.register(execute_command, persistent=True)
        self.report({'INFO'}, f"Claude Bridge listening at {BRIDGE_DIR}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(ClaudeBridgeOperator)
    os.makedirs(BRIDGE_DIR, exist_ok=True)
    if not bpy.app.timers.is_registered(execute_command):
        bpy.app.timers.register(execute_command, persistent=True)
    print(f"Claude Bridge: listening at {BRIDGE_DIR}")


def unregister():
    if bpy.app.timers.is_registered(execute_command):
        bpy.app.timers.unregister(execute_command)
    bpy.utils.unregister_class(ClaudeBridgeOperator)


if __name__ == "__main__":
    register()
