#!/bin/bash
set -e

WATCH_DIR="$HOME/.unity_code_executor"
INPUT_FILE="$WATCH_DIR/input.cs"
OUTPUT_FILE="$WATCH_DIR/output.jsonl"

# Check if Unity is running
if ! pgrep -x "Unity" > /dev/null; then
    echo "Error: Unity Editor must be running"
    exit 1
fi

usage() {
    echo "Usage: $0 [-f <file.cs>] [-c <code>]"
    echo "  -f <file>   Run C# code from file"
    echo "  -c <code>   Run inline C# code"
    echo ""
    echo "Examples:"
    echo "  $0 -c 'Debug.Log(Application.unityVersion);'"
    echo "  $0 -f /tmp/myscript.cs"
    exit 1
}

if [ $# -eq 0 ]; then
    usage
fi

CODE=""
CODE_FILE=""

while getopts "f:c:h" opt; do
    case $opt in
        f)
            CODE_FILE="$OPTARG"
            ;;
        c)
            CODE="$OPTARG"
            ;;
        h)
            usage
            ;;
        *)
            usage
            ;;
    esac
done

# Determine the code to run
if [ -n "$CODE_FILE" ]; then
    if [ ! -f "$CODE_FILE" ]; then
        echo "Error: File not found: $CODE_FILE"
        exit 1
    fi
    CODE=$(cat "$CODE_FILE")
elif [ -z "$CODE" ]; then
    usage
fi

# Ensure watch directory exists
mkdir -p "$WATCH_DIR"

# Count lines before execution (0 if file doesn't exist)
if [ -f "$OUTPUT_FILE" ]; then
    LINES_BEFORE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
else
    LINES_BEFORE=0
fi

# Write code to input file
echo "$CODE" > "$INPUT_FILE"

# Wait for input file to be consumed (Unity deletes it after reading)
TIMEOUT=30
for i in $(seq 1 $TIMEOUT); do
    if [ ! -f "$INPUT_FILE" ]; then
        # Input consumed, wait a tiny bit for logs to be written
        sleep 0.1
        break
    fi
    sleep 0.5
done

if [ -f "$INPUT_FILE" ]; then
    echo "Timeout waiting for Unity to consume input after ${TIMEOUT}s"
    exit 1
fi

# Get new lines (diff)
if [ -f "$OUTPUT_FILE" ]; then
    LINES_AFTER=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
    if [ "$LINES_AFTER" -gt "$LINES_BEFORE" ]; then
        # Show new lines, formatted with type prefix
        tail -n +$((LINES_BEFORE + 1)) "$OUTPUT_FILE" | while IFS= read -r line; do
            # Parse JSONL and format output
            msg=$(echo "$line" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p' | sed 's/\\n/\n/g; s/\\t/\t/g; s/\\"/"/g; s/\\\\/\\/g')
            type=$(echo "$line" | sed -n 's/.*"type":"\([^"]*\)".*/\1/p')
            case "$type" in
                error|assert|exception)
                    echo "[$type] $msg"
                    ;;
                warning)
                    echo "[$type] $msg"
                    ;;
                *)
                    echo "$msg"
                    ;;
            esac
        done
    fi
fi
