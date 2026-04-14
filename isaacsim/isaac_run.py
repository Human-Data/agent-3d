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

Env: ISAAC_BRIDGE_HOST (127.0.0.1), ISAAC_BRIDGE_PORT (8723), ISAAC_RUN_TIMEOUT (60s, 0 = none).
"""

import json
import os
import socket
import sys

HOST = os.environ.get("ISAAC_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ISAAC_BRIDGE_PORT", "8723"))
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


def connect():
    try:
        return socket.create_connection((HOST, PORT), timeout=5)
    except OSError as e:
        sys.exit(f"ERROR: no Isaac Sim bridge at {HOST}:{PORT} ({e}). Isaac Sim still loading, or bridge not started. "
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
