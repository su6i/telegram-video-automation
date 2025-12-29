#!/usr/bin/env python3
"""
Debug script to check pagination issues
"""

import sys
sys.path.insert(0, '/Users/su6i/@-github/telegram-video-automation')

from src.scrapers.primary_scraper import PrimaryScraper

print("🔍 Testing AI Creator Course pagination...\n")

scraper = PrimaryScraper()
course_url = "https://ai-creator-course.kajabi.com/"

# Track what we find
videos = scraper.get_video_links(limit=None)

print(f"\n\n📊 Summary:")
print(f"   Total videos found: {len(videos)}")

# Group by section
from collections import defaultdict
by_section = defaultdict(int)
for v in videos:
    section = v.get('section', 'Unknown')
    by_section[section] += 1

print(f"\n   By section:")
for section in sorted(by_section.keys()):
    print(f"      - {section}: {by_section[section]} videos")

# Show if we have duplicates
urls = [v['url'] for v in videos]
if len(urls) != len(set(urls)):
    print(f"\n   ⚠️ WARNING: Found {len(urls) - len(set(urls))} duplicate URLs!")
else:
    print(f"\n   ✅ No duplicates found")

# Check pagination
print(f"\n   Check if all sections are covered:")
print(f"      - AI Video Creation should have ~11 videos")
print(f"      - AI Video Editing should have ~8 videos")
