#!/bin/bash
# Full Course Archive Tool
# Downloads Videos, Archives HTML Pages, and Extracts Resources.

set -e

# Project root is one level up from tools/
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "🚀 Starting Full Archive Pipeline"
echo "=========================================="

# Step 1: Download Videos
echo "📼 Step 1: Downloading Videos..."
python3 scripts/course_scraper.py --download

# Step 2: Archive Pages
echo "📚 Step 2: Archiving Course Pages (HTML + Assets)..."
python3 scripts/scan_and_archive_pages.py

# Step 3: Extract Resources
echo "🔗 Step 3: Extracting Resources (Links + Descriptions)..."
python3 scripts/download_resources.py --all

echo "=========================================="
echo "🎉 Full Archive Complete!"
echo "=========================================="
echo "📁 Data organized in .storage/ and downloads/"
