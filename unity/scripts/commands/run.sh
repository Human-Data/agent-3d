cmd_run() {
    local src
    if [[ $# -eq 0 ]]; then
        src="$(cat)"            # no args: read the C# source from stdin
    elif [[ $# -eq 1 && -f "$1" ]]; then
        src="$(cat "$1")"
    else
        src="$*"
    fi
    local b64
    b64="$(printf '%s' "$src" | base64 | tr -d '\n')"
    send "RunCommand" "$b64";
}
