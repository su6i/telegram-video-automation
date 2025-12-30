#!/bin/bash
# Unified Upload Script
# This script processes and uploads videos to Telegram based on the manifest.

# Default values
RES=720
INTRO=false
INDEX_OFFSET=0

# Help message
function show_help() {
    echo "Usage: ./upload.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --res 720|1080       Target resolution (default: 720)"
    echo "  --intro              Add title card intro (default: false)"
    echo "  --index-offset ID    Start Index from this Message ID"
    echo "  --help               Show this help message"
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --res) RES="$2"; shift ;;
        --intro) INTRO=true ;;
        --index-offset) INDEX_OFFSET="$2"; shift ;;
        --help) show_help; exit 0 ;;
        *) echo "Unknown parameter passed: $1"; show_help; exit 1 ;;
    esac
    shift
done

echo "🚀 Starting upload process..."
echo "📊 Settings: Resolution=${RES}p, Add Intro=${INTRO}, Index Offset=${INDEX_OFFSET}"

# Check for virtual environment
if [ -f ".venv/bin/activate" ]; then
    echo "🌐 Activating virtual environment..."
    source .venv/bin/activate
fi

# Run the python script
CMD="python3 scripts/process_and_upload.py --res $RES"
if [[ "$INTRO" == "true" ]]; then
    CMD="$CMD --intro"
fi
if [[ "$INDEX_OFFSET" -gt 0 ]]; then
    CMD="$CMD --index-offset $INDEX_OFFSET"
fi

$CMD

echo "✅ Upload sequence finished."
