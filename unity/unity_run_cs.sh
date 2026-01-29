#!/bin/bash
set -e

WATCH_DIR="$HOME/.unity_code_executor"
INPUT_FILE="$WATCH_DIR/input.cs"
UNITY_LOG="$HOME/Library/Logs/Unity/Editor.log"

# Check if Unity is running
if ! pgrep -x "Unity" > /dev/null; then
    echo "Error: Unity Editor must be running"
    exit 1
fi

usage() {
    echo "Usage: $0 [-f <file.cs>] or pipe/redirect via stdin (heredoc)"
    echo "  -f <file>   Run C# code from file"
    echo "  stdin       Read C# code from stdin (heredoc/pipe) - PREFERRED"
    echo ""
    echo "Examples:"
    echo "  # Using heredoc (recommended - no escaping issues!):"
    echo "  $0 <<'EOF'"
    echo "  Debug.Log(\"Hello!\");"
    echo "  Debug.Log(\$\"Unity {Application.unityVersion}\");"
    echo "  EOF"
    echo ""
    echo "  # Using file:"
    echo "  $0 -f /tmp/myscript.cs"
    exit 1
}

CODE=""

# Check if stdin is available (not a terminal)
if [ ! -t 0 ]; then
    # Read from stdin
    CODE=$(cat)
else
    # Parse options for file input only
    if [ $# -eq 0 ]; then
        usage
    fi

    while getopts "f:h" opt; do
        case $opt in
            f)
                if [ ! -f "$OPTARG" ]; then
                    echo "Error: File not found: $OPTARG"
                    exit 1
                fi
                CODE=$(cat "$OPTARG")
                ;;
            h)
                usage
                ;;
            *)
                usage
                ;;
        esac
    done

    if [ -z "$CODE" ]; then
        echo "Error: No code provided. Use stdin (heredoc) or -f <file>"
        echo ""
        usage
    fi
fi

# Ensure watch directory exists
mkdir -p "$WATCH_DIR"

# Count lines before execution
if [ -f "$UNITY_LOG" ]; then
    LINES_BEFORE=$(wc -l < "$UNITY_LOG" | tr -d ' ')
else
    echo "Error: Unity Editor log not found at $UNITY_LOG"
    exit 1
fi

# Write code to input file
echo "$CODE" > "$INPUT_FILE"

# Wait for input file to be consumed (Unity deletes it after reading)
TIMEOUT=30
for i in $(seq 1 $TIMEOUT); do
    if [ ! -f "$INPUT_FILE" ]; then
        # Input consumed, wait for code execution and logs to be written
        sleep 2
        break
    fi
    sleep 0.5
done

if [ -f "$INPUT_FILE" ]; then
    echo "Timeout waiting for Unity to consume input after ${TIMEOUT}s"
    exit 1
fi

# Get new lines from Unity log
LINES_AFTER=$(wc -l < "$UNITY_LOG" | tr -d ' ')
if [ "$LINES_AFTER" -gt "$LINES_BEFORE" ]; then
    # Show new lines, filter out stack traces and system messages
    tail -n +$((LINES_BEFORE + 1)) "$UNITY_LOG" | grep -v '^ #[0-9]' | grep -v '^$' | grep -v '^\[CodeExecutor\]'
fi
