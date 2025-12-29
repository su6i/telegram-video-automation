#!/bin/bash
# Unified Upload Script
# This script processes and uploads videos to Telegram based on the manifest.

# Default values
RES=720
INTRO=false

# Help message
function show_help() {
    echo "Usage: ./upload.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --res 720|1080    Target resolution (default: 720)"
    echo "  --intro           Add title card intro (default: false)"
    echo "  --help            Show this help message"
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --res) RES="$2"; shift ;;
        --intro) INTRO=true ;;
        --help) show_help; exit 0 ;;
        *) echo "Unknown parameter passed: $1"; show_help; exit 1 ;;
    esac
    shift
done

echo "🚀 Starting upload process..."
echo "📊 Settings: Resolution=${RES}p, Add Intro=${INTRO}"

# Run the python script
if [[ "$INTRO" == "true" ]]; then
    python3 scripts/process_and_upload.py --res "$RES" --intro
else
    python3 scripts/process_and_upload.py --res "$RES"
fi

echo "✅ Upload sequence finished."
