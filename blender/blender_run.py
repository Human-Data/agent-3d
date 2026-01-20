#!/usr/bin/env python3
"""
Send Python code to a running Blender instance via Claude Bridge addon.
"""

import argparse
import os
import sys
import tempfile
import time

BRIDGE_DIR = os.path.join(tempfile.gettempdir(), "blender_claude_bridge")
CMD_FILE = os.path.join(BRIDGE_DIR, "command.py")
RESULT_FILE = os.path.join(BRIDGE_DIR, "result.txt")
LOCK_FILE = os.path.join(BRIDGE_DIR, "lock")

TIMEOUT = 30  # seconds


def run_code(code: str) -> tuple[str, int]:
    """
    Send code to Blender and wait for result.

    Returns:
        Tuple of (output, return_code)
    """
    os.makedirs(BRIDGE_DIR, exist_ok=True)

    # Clean up old result
    if os.path.exists(RESULT_FILE):
        os.remove(RESULT_FILE)

    # Create lock file
    with open(LOCK_FILE, 'w') as f:
        f.write("")

    # Write command
    with open(CMD_FILE, 'w') as f:
        f.write(code)

    # Wait for result
    start = time.time()
    while time.time() - start < TIMEOUT:
        if os.path.exists(RESULT_FILE) and not os.path.exists(LOCK_FILE):
            with open(RESULT_FILE, 'r') as f:
                lines = f.read()

            # Parse status
            if lines.startswith("OK\n"):
                return lines[3:], 0
            elif lines.startswith("ERROR\n"):
                return lines[6:], 1
            else:
                return lines, 0

        time.sleep(0.05)

    return "ERROR: Timeout - is Blender running with Claude Bridge addon enabled?", 1


def main():
    parser = argparse.ArgumentParser(description="Run Python code in Blender")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--code", help="Python code to execute")
    group.add_argument("-f", "--file", help="Python file to execute")

    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r') as f:
            code = f.read()
    else:
        code = args.code

    # Fix shell escaping artifacts - when passing code via bash single quotes,
    # escaped quotes \" are passed literally but break Python f-string expressions.
    # Only convert \" to ' inside f-string curly brace expressions {}.
    import re
    def fix_fstring_escapes(match):
        # Replace \" with ' only inside the f-string expression
        return match.group(0).replace('\\"', "'")
    # Match content inside {} that might contain escaped quotes
    # This pattern finds {expressions} and fixes escapes within them
    code = re.sub(r'\{[^{}]*\\\"[^{}]*\}', fix_fstring_escapes, code)

    output, returncode = run_code(code)
    print(output, end="" if output.endswith("\n") else "\n")
    sys.exit(returncode)


if __name__ == "__main__":
    main()
