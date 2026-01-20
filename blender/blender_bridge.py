"""
Claude Bridge - Minimal Blender addon for external code execution.
Watches a command file and executes Python code sent from outside.
"""

bl_info = {
    "name": "Claude Bridge",
    "author": "Claude",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "Runs in background",
    "description": "Execute Python code from external scripts",
    "category": "Development",
}

import bpy
import os
import tempfile
import traceback

# Communication files
BRIDGE_DIR = os.path.join(tempfile.gettempdir(), "blender_claude_bridge")
CMD_FILE = os.path.join(BRIDGE_DIR, "command.py")
RESULT_FILE = os.path.join(BRIDGE_DIR, "result.txt")
LOCK_FILE = os.path.join(BRIDGE_DIR, "lock")


def ensure_bridge_dir():
    os.makedirs(BRIDGE_DIR, exist_ok=True)


def execute_command():
    """Check for and execute pending commands."""
    if not os.path.exists(CMD_FILE):
        return 0.1  # Check every 100ms

    try:
        # Read command
        with open(CMD_FILE, 'r') as f:
            code = f.read()

        # Remove command file immediately
        os.remove(CMD_FILE)

        # Execute code
        output_lines = []

        # Capture print output
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        try:
            # Execute with bpy available
            exec(code, {"bpy": bpy, "__builtins__": __builtins__})
            output = sys.stdout.getvalue()
            output_lines.append(output)
            status = "OK"
        except Exception as e:
            output_lines.append(f"ERROR: {e}\n{traceback.format_exc()}")
            status = "ERROR"
        finally:
            sys.stdout = old_stdout

        # Write result
        with open(RESULT_FILE, 'w') as f:
            f.write(f"{status}\n")
            f.write("\n".join(output_lines))

        # Signal completion
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)

    except Exception as e:
        print(f"Claude Bridge error: {e}")

    return 0.1


class ClaudeBridgeOperator(bpy.types.Operator):
    """Start the Claude Bridge listener"""
    bl_idname = "claude.bridge_start"
    bl_label = "Start Claude Bridge"

    def execute(self, context):
        ensure_bridge_dir()
        bpy.app.timers.register(execute_command, persistent=True)
        self.report({'INFO'}, f"Claude Bridge listening at {BRIDGE_DIR}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(ClaudeBridgeOperator)
    ensure_bridge_dir()
    # Auto-start on addon load
    if not bpy.app.timers.is_registered(execute_command):
        bpy.app.timers.register(execute_command, persistent=True)
    print(f"Claude Bridge: listening at {BRIDGE_DIR}")


def unregister():
    if bpy.app.timers.is_registered(execute_command):
        bpy.app.timers.unregister(execute_command)
    bpy.utils.unregister_class(ClaudeBridgeOperator)


if __name__ == "__main__":
    register()
