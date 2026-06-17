cmd_editor() {
    local sub="${1:-}"; shift || true
    case "$sub" in
        play)  send "Play";;
        pause) send "Pause";;
        stop)  send "Stop";;
        state) send "GetEditorState";;
        *)     echo "error: unknown 'editor' subcommand '$sub' (try: play, pause, stop, state)" >&2; exit 2;;
    esac
}
