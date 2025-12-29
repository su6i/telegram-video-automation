#!/usr/bin/env python3
"""
Download all course resources: descriptions, downloadable files, documents.
This complements the video downloader.

Usage:
    python scripts/download_resources.py --archive-pages    # Download HTML pages
    python scripts/download_resources.py --extract-links     # Save all links
    python scripts/download_resources.py --all               # Do everything
"""

import os
import sys
import json
import requests
import argparse
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.page_archiver import archive_page, list_archived_pages
from src.scrapers.primary_scraper import PrimaryScraper

STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")
RESOURCES_DIR = os.path.join(STORAGE_DIR, "resources")
LINKS_LOG = os.path.join(STORAGE_DIR, "all_links.json")


def extract_urls_from_manifest():
    """Extract all lesson URLs from manifest."""
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
                        # Skip Wistia video links, we want lesson pages
                        urls.append({'url': url, 'title': title})
    
    return urls


def archive_all_pages():
    """Archive all lesson pages as HTML with assets."""
    print("\n" + "="*60)
    print("📚 Archiving all course pages...")
    print("="*60)
    
    urls = extract_urls_from_manifest()
    
    if not urls:
        print("⚠️ No lesson pages found to archive")
        return
    
    print(f"Found {len(urls)} lessons to archive\n")
    
    successful = 0
    failed = 0
    
    for i, item in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {item['title'][:40]}...")
        result = archive_page(item['url'], item['title'])
        
        if result.get('success'):
            successful += 1
        else:
            failed += 1
        
        # Small delay between requests
        import time
        if i < len(urls):
            time.sleep(0.5)
    
    print("\n" + "="*60)
    print(f"✅ Archive Complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  📁 Location: {os.path.abspath(os.path.join(STORAGE_DIR, 'page_archives'))}")
    print("="*60)


def extract_all_links():
    """Extract all resource links from descriptions."""
    print("\n" + "="*60)
    print("🔗 Extracting all resource links...")
    print("="*60)
    
    if not os.path.exists(CONTENT_FILE):
        print(f"❌ Content file not found: {CONTENT_FILE}")
        print("   Run --scan first to collect descriptions")
        return
    
    with open(CONTENT_FILE, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    all_links = {}
    
    for video_url, data in content.items():
        if not data.get('links'):
            continue
        
        video_title = data.get('title', 'Unknown')
        all_links[video_title] = {
            'video_url': video_url,
            'links': data.get('links', []),
            'resource_count': len(data.get('links', []))
        }
    
    # Save links log
    os.makedirs(STORAGE_DIR, exist_ok=True)
    with open(LINKS_LOG, 'w', encoding='utf-8') as f:
        json.dump(all_links, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Summary:")
    print(f"  Videos with resources: {len(all_links)}")
    
    total_resources = sum(v['resource_count'] for v in all_links.values())
    print(f"  Total resource links: {total_resources}")
    
    # Print sample
    print(f"\n📌 Sample resources:")
    for title, data in list(all_links.items())[:3]:
        print(f"\n  📄 {title}")
        for link in data['links'][:2]:
            print(f"     • {link.get('text', 'Link')}: {link.get('url', 'N/A')[:60]}...")
    
    print("\n" + "="*60)
    print(f"✅ Links extracted: {os.path.abspath(LINKS_LOG)}")
    print("="*60)


def save_descriptions():
    """Save all video descriptions to text files."""
    print("\n" + "="*60)
    print("📝 Saving all descriptions...")
    print("="*60)
    
    if not os.path.exists(CONTENT_FILE):
        print(f"❌ Content file not found: {CONTENT_FILE}")
        return
    
    with open(CONTENT_FILE, 'r', encoding='utf-8') as f:
        content = json.load(f)
    
    descriptions_dir = os.path.join(STORAGE_DIR, "descriptions")
    os.makedirs(descriptions_dir, exist_ok=True)
    
    count = 0
    for video_url, data in content.items():
        title = data.get('title', 'Unknown')
        description = data.get('description', '')
        
        if not description:
            continue
        
        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
        safe_title = safe_title[:60]
        
        filename = f"{safe_title}.txt"
        filepath = os.path.join(descriptions_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"📺 {title}\n")
            f.write(f"URL: {video_url}\n")
            f.write("="*60 + "\n\n")
            f.write(description)
        
        count += 1
    
    print(f"✅ Saved {count} descriptions to: {os.path.abspath(descriptions_dir)}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Download course resources (pages, links, descriptions)"
    )
    parser.add_argument(
        "--archive-pages",
        action="store_true",
        help="Download all lesson pages as HTML with images"
    )
    parser.add_argument(
        "--extract-links",
        action="store_true",
        help="Extract all resource links from descriptions"
    )
    parser.add_argument(
        "--save-descriptions",
        action="store_true",
        help="Save descriptions to individual text files"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Do everything"
    )
    
    args = parser.parse_args()
    
    if args.all or args.archive_pages:
        archive_all_pages()
    
    if args.all or args.extract_links:
        extract_all_links()
    
    if args.all or args.save_descriptions:
        save_descriptions()
    
    if not any([args.all, args.archive_pages, args.extract_links, args.save_descriptions]):
        parser.print_help()
        print("\n💡 Examples:")
        print("   python scripts/download_resources.py --archive-pages")
        print("   python scripts/download_resources.py --extract-links")
        print("   python scripts/download_resources.py --all")


if __name__ == "__main__":
    main()
