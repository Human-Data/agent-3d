#!/usr/bin/env python3
"""
Run Python code in a live Blender instance (via the Claude Bridge addon).

Usage:
    blender_run.py 'print(bpy.context.scene.name)'   # one-liner argument
    blender_run.py <<'EOF'                            # multi-line heredoc
    for obj in bpy.context.scene.objects:
        print(obj.name)
    EOF
    blender_run.py < script.py                        # from a file
"""

import os
import sys
import tempfile
import time
import uuid

BRIDGE_DIR = os.path.join(tempfile.gettempdir(), "blender_claude_bridge")

try:
    TIMEOUT = float(os.environ.get("BLENDER_RUN_TIMEOUT", "30"))
except ValueError:
    TIMEOUT = 30.0


def main():
    if len(sys.argv) > 2:
        sys.exit("usage: blender_run.py ['code']   (or pipe code via stdin/heredoc)")
    code = sys.argv[1] if len(sys.argv) == 2 else sys.stdin.read()
    if not code.strip():
        sys.exit("error: no code given (pass as argument or via stdin)")

    os.makedirs(BRIDGE_DIR, exist_ok=True)
    req_id = uuid.uuid4().hex
    cmd_file = os.path.join(BRIDGE_DIR, f"cmd-{req_id}.py")
    result_file = os.path.join(BRIDGE_DIR, f"result-{req_id}.txt")

    # temp + rename so the bridge can never read a half-written script
    tmp = os.path.join(BRIDGE_DIR, f".cmd-{req_id}.tmp")
    with open(tmp, "w") as f:
        f.write(code)
    os.replace(tmp, cmd_file)

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if os.path.exists(result_file):
            with open(result_file) as f:
                result = f.read()
            os.remove(result_file)
            status, _, output = result.partition("\n")
            print(output, end="" if output.endswith("\n") or not output else "\n")
            sys.exit(1 if status == "ERROR" else 0)
        time.sleep(0.05)

    try:  # don't leave the command to run whenever Blender next starts
        os.remove(cmd_file)
    except OSError:
        pass
    sys.exit("ERROR: Timeout - is Blender running with the Claude Bridge addon enabled?"
             " (setup: ~/.claude/skills/blender/install.sh)")


if __name__ == "__main__":
    main()
