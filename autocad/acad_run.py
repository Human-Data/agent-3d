#!/usr/bin/env python3
"""
Run AutoLISP code in a live AutoCAD instance (via acad_bridge.lsp).

Usage:
    acad_run.py '(getvar "DWGNAME")'   # one-liner argument
    acad_run.py <<'EOF'                # multi-line heredoc
    (princ (getvar "CLAYER"))
    EOF
    acad_run.py < script.lsp           # from a file

How it works: the code is written to bridge/cmd-<id>.lsp, one expression is typed
at AutoCAD's command line (COM SendCommand) that
loads the bridge and runs the file, and the bridge writes bridge/result-<id>.txt,
which is printed here.
"""

import os
import subprocess
import sys
import time
import uuid

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_LSP = os.path.join(SKILL_DIR, "acad_bridge.lsp")
BRIDGE_DIR = os.path.join(SKILL_DIR, "bridge")

TIMEOUT = 30.0


def lisp_str(s):
    """Quote a Python string as an AutoLISP string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --- getting one expression onto AutoCAD's command line -------------------

def send(expr):
    """COM: AutoCAD.Application -> ActiveDocument.SendCommand. Uses the built-in
    Windows PowerShell 5.1 so no Python packages are needed."""
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    script = (
        "$ErrorActionPreference='Stop';"
        "try {"
        "  $a=[Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application');"
        "  $a.ActiveDocument.SendCommand($env:ACAD_CMD)"
        "} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
    )
    env = dict(os.environ, ACAD_CMD=expr + "\n")  # env var: no quoting issues
    r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", script],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: could not send to AutoCAD: {r.stderr.strip()}")


# --- request / response over the bridge dir -------------------------------

def run(code):
    os.makedirs(BRIDGE_DIR, exist_ok=True)
    req_id = uuid.uuid4().hex
    cmd_file = os.path.join(BRIDGE_DIR, f"cmd-{req_id}.lsp")
    result_file = os.path.join(BRIDGE_DIR, f"result-{req_id}.txt")

    # temp + rename so AutoCAD can never load a half-written script
    tmp = cmd_file + ".tmp"
    with open(tmp, "w", errors="replace") as f:
        f.write(code if code.endswith("\n") else code + "\n")
    os.replace(tmp, cmd_file)

    send(f"(progn (load {lisp_str(BRIDGE_LSP)}) (claude-run {lisp_str(cmd_file)} {lisp_str(result_file)}))")

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if os.path.exists(result_file):
            with open(result_file, errors="replace") as f:
                result = f.read()
            os.remove(result_file)
            status, _, output = result.partition("\n")
            print(output, end="")
            sys.exit(1 if status.strip() == "ERROR" else 0)
        time.sleep(0.05)

    try:  # don't leave the script lying around for a later run
        os.remove(cmd_file)
    except OSError:
        pass
    sys.exit("ERROR: Timeout - no reply from AutoCAD. Is it idle at the Command: prompt?")


def main():
    if len(sys.argv) > 2:
        sys.exit("usage: acad_run.py ['code']   (or pipe code via stdin/heredoc)")
    code = sys.argv[1] if len(sys.argv) == 2 else sys.stdin.read()
    if not code.strip():
        sys.exit("error: no code given (pass as argument or via stdin)")
    run(code)


if __name__ == "__main__":
    main()
