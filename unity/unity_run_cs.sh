#!/bin/bash
set -e

WATCH_DIR="$HOME/.unity_code_executor"
INPUT_FILE="$WATCH_DIR/input.cs"
OUTPUT_FILE="$WATCH_DIR/output.txt"

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

# Remove old output file
rm -f "$OUTPUT_FILE"

# Write code to input file
echo "$CODE" > "$INPUT_FILE"

# Wait for output (poll with timeout)
TIMEOUT=30
for i in $(seq 1 $TIMEOUT); do
    if [ -f "$OUTPUT_FILE" ]; then
        cat "$OUTPUT_FILE"
        # Check if it was an error
        if grep -q "^ERROR:" "$OUTPUT_FILE"; then
            exit 1
        fi
        exit 0
    fi
    sleep 0.5
done

echo "Timeout waiting for Unity response after ${TIMEOUT}s"
exit 1
