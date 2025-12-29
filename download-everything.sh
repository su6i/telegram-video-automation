#!/bin/bash
# Download Everything: Videos + Archive Pages + Resources
# Usage: ./download-everything.sh

set -e

echo "=========================================="
echo "🚀 Complete Course Download"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Download Videos
echo -e "${BLUE}📼 Step 1: Downloading Videos...${NC}"
python scripts/smart_scraper.py --download
echo -e "${GREEN}✅ Videos downloaded${NC}\n"

# Step 2: Archive Pages
echo -e "${BLUE}📚 Step 2: Archiving Course Pages (HTML + Images)...${NC}"
python scripts/scan_and_archive_pages.py
echo -e "${GREEN}✅ Pages archived${NC}\n"

# Step 3: Extract Resources
echo -e "${BLUE}🔗 Step 3: Extracting Resources (Links + Descriptions)...${NC}"
python scripts/download_resources.py --all
echo -e "${GREEN}✅ Resources extracted${NC}\n"

# Summary
echo "=========================================="
echo -e "${GREEN}🎉 All Done!${NC}"
echo "=========================================="
echo ""
echo "📁 Files organized in:"
echo "   📼 Videos:      downloads/"
echo "   📚 Pages:       .storage/page_archives/"
echo "   🔗 Links:       .storage/all_links.json"
echo "   📝 Descriptions: .storage/descriptions/"
echo ""
echo "👉 To view downloads:"
echo "   open downloads/"
echo ""
