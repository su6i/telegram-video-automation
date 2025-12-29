#!/bin/bash
"$(dirname "$0")/.venv/bin/python" scripts/scraper.py --scan "$@"
