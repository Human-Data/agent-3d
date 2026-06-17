#!/usr/bin/env bash
# Talk to Unity's bridge over its deterministic Unix domain socket.
#
# Usage:
#   unity.sh [-p <project-root>] <command> [args...]
#
# Commands (each implemented in commands/<command>.sh):
#   run <string|file|->      run an arbitrary C# script (inline arg, .cs file, or stdin heredoc)
#   build --target iOS [--sim|--device] export a build (--output defaults to /tmp/unitybuild-ios-XXXX.)
#   log get [maxCount]       fetch console log entries (default 100; <=0 = no limit)
#   log clear                clear the Editor console
#   editor play              enter play mode
#   editor pause             toggle pause/resume
#   editor stop              exit play mode
#   editor state             editor state snapshot (isPlaying/isPaused/isCompiling/...)
#   asset reimport           AssetDatabase.Refresh() — reimport changed assets
#   editor-window-capture [window] (e.g. SceneView, GameView, InspectorWindow, ConsoleWindow, ProjectBrowser)
#   editor-window-open [--new] [--rect x,y,w,h] [window]   open/focus a window (--new = new instance)
#   editor-window-open --asset <path>                      open an asset in its editor (e.g. .uxml -> UI Builder)
#
# Project root resolution (must match the path the Editor logs as "hash input"):
#   1. -p / --project <path>
#   2. $UNITY_PROJECT_ROOT
#   3. the current working directory  (default)
set -euo pipefail

USAGE="commands: run, build --target iOS [--sim|--device] [--output <dir>], log {get|clear}, editor {play|pause|stop|state}, asset reimport, editor-window-capture [window], editor-window-open [--new|--asset] [window|path]"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD_DIR="$SCRIPT_DIR/commands"

# ── transport ──────────────────────────────────────────────────────────────
send() { printf '%s\n' "$*" | nc -U "$SOCK"; }


P="${UNITY_PROJECT_ROOT:-$PWD}"
if [[ "${1:-}" == "-p" || "${1:-}" == "--project" ]]; then
    [[ $# -ge 2 ]] || { echo "error: $1 needs a path" >&2; exit 2; }
    P="$2"; shift 2
fi
[[ $# -ge 1 ]] || { echo "usage: $(basename "$0") [-p <project-root>] <command> [args]  ($USAGE)" >&2; exit 2; }
cmd="$1"; shift

# ── resolve the deterministic socket from the project root ───────────────────
P="${P%/}"   # strip a trailing slash so the hash matches the Editor side
if command -v md5 >/dev/null 2>&1; then
    hash="$(md5 -q -s "$P" | cut -c1-8)"          # macOS
else
    hash="$(printf '%s' "$P" | md5sum | cut -c1-8)" # Linux (same digest)
fi
SOCK="/tmp/unity-mini-${hash}.sock"
[[ -S "$SOCK" ]] || { echo "error: no server socket at $SOCK (is the Unity Editor open for project '$P'?)" >&2; exit 1; }

[[ "$cmd" =~ ^[a-z][a-z-]*$ ]] || { echo "error: unknown command '$cmd' ($USAGE)" >&2; exit 2; }
CMD_FILE="$CMD_DIR/$cmd.sh"
[[ -f "$CMD_FILE" ]] || { echo "error: unknown command '$cmd' ($USAGE)" >&2; exit 2; }

# cmd_run is a shared dependency (asset / editor-window-* call it); load it first.
source "$CMD_DIR/run.sh"
[[ "$cmd" == "run" ]] || source "$CMD_FILE"

declare -f "cmd_$cmd" >/dev/null || { echo "error: command '$cmd' has no cmd_$cmd implementation in $CMD_FILE" >&2; exit 2; }
"cmd_$cmd" "$@"
