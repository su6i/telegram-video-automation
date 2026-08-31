#!/usr/bin/env python3
"""
Unified Entry Point for Telegram Video Automation
Target: World-Class Open Source Standards
"""
import os
import sys
import argparse
from dotenv import load_dotenv

# Ensure we can import from src and scripts
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))

try:
    from src.i18n import t
    from scripts.scraper import scan_videos, download_videos, archive_manifest_pages, process_single_url
except ImportError as e:
    print(f"❌ Critical Import Error: {e}")
    sys.exit(1)

def setup_environment():
    load_dotenv()
    # verify essential env vars if needed
    pass

def main():
    setup_environment()
    
    parser = argparse.ArgumentParser(description="Telegram Video Automation - Unified CLI")
    
    # Positional URL (Optional)
    parser.add_argument("input_url", nargs="?", help="Direct URL to process")

    # Mode Selection
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", help="Download a single lesson (Legacy Flag)")
    group.add_argument("--scan", action="store_true", help="Scan the target site and update the video manifest")
    group.add_argument("--download", action="store_true", help="Batch download videos from the manifest")
    group.add_argument("--archive", action="store_true", help="Archive HTML pages listed in the manifest")
    
    # Options
    parser.add_argument("--force", action="store_true", help="Force overwrite existing files")
    parser.add_argument("--limit", type=int, help="Limit operation to N items")
    parser.add_argument("--update-metadata", action="store_true", help="Force rescan of metadata during scan")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode (not headless)")
    parser.add_argument("--offset", type=int, default=0, help="Skip N items at start")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Environment config based on flags
    if args.visible:
        os.environ["HEADLESS_MODE"] = "false"
    else: 
        os.environ["HEADLESS_MODE"] = "true"

    print(t("welcome"))
    print("================================")

    target_url = args.input_url or args.url

    if target_url:
        # If --scan is PRESENT, we do NOT download.
        do_download = not args.scan
        process_single_url(target_url, verbose=args.verbose, download=do_download)
    elif args.scan:
        scan_videos(limit=args.limit, update_metadata=args.update_metadata, offset=args.offset, verbose=args.verbose)
    elif args.download:
        download_videos(force=args.force)
    elif args.archive:
        archive_manifest_pages()
    else:
        parser.print_help()
        print(f"\n{t('error_no_action')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
