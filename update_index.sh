#!/bin/bash
# Wrapper to run the index generator using the local venv

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$DIR"

# Activate venv and run
"$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/generate_index.py"
