#!/usr/bin/env python
"""
Scan and archive course pages locally with all assets.
Usage: python scripts/scan_and_archive_pages.py
"""
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.page_archiver import archive_page, list_archived_pages
from src.scrapers.primary_scraper import PrimaryScraper


STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")


def extract_urls_from_manifest():
    """Extract video URLs from manifest."""
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest not found: {MANIFEST_FILE}")
        return []
    
    urls = []
    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '|' in line and not line.startswith('#'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    url = parts[2]  # URL is 3rd part (after Index | Title)
                    title = parts[1] if len(parts) > 1 else None
                    if url.startswith('http') and 'wistia' not in url:
                        # Get lesson page URLs, not video embeds
                        urls.append({'url': url, 'title': title})
    
    return urls


def main():
    """Main archive workflow."""
    print("=" * 60)
    print("📚 Course Page Archiver")
    print("=" * 60)
    
    # Extract URLs from manifest
    print("\n🔍 Extracting URLs from manifest...")
    urls = extract_urls_from_manifest()
    
    if not urls:
        print("❌ No URLs found in manifest")
        return
    
    print(f"📋 Found {len(urls)} pages to archive")
    
    # Archive each page
    print("\n" + "=" * 60)
    results = []
    for i, item in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] Archiving: {item['title']}")
        result = archive_page(item['url'], item['title'])
        results.append(result)
        
        # Add small delay between requests
        import time
        if i < len(urls):
            time.sleep(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Archive Summary")
    print("=" * 60)
    
    successful = sum(1 for r in results if r.get('success'))
    failed = len(results) - successful
    
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    
    if successful > 0:
        print(f"\n📁 Pages archived to: .storage/page_archives/")
        
        # List archived pages
        archived = list_archived_pages()
        print(f"\n📚 Archived Pages ({len(archived)}):")
        for page in archived:
            print(f"  • {page.get('title', 'Unknown')}")
            print(f"    🖼️ {len(page.get('images', []))} images")
            print(f"    🔗 {len(page.get('links', []))} links")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
