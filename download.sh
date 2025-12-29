#!/bin/bash
"$(dirname "$0")/.venv/bin/python" scripts/course_scraper.py --download "$@"
