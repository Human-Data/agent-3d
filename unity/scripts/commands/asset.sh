cmd_asset() {
    local sub="${1:-}"; shift || true
    case "$sub" in
        reimport) cmd_run 'using UnityEditor; class Cmd : IRunCommand { public void Execute() { AssetDatabase.Refresh(); } }';;
        *)        echo "error: unknown 'asset' subcommand '$sub' (try: reimport)" >&2; exit 2;;
    esac
}
