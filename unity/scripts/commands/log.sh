cmd_log() {
    local sub="${1:-}"; shift || true
    case "$sub" in
        get)   send "GetLog" "$@";;   # optional maxCount passed through
        clear) send "ClearLog";;
        *)     echo "error: unknown 'log' subcommand '$sub' (try: get, clear)" >&2; exit 2;;
    esac
}
