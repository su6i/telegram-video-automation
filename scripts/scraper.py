import os
import sys
import argparse
import concurrent.futures
from tqdm import tqdm
import yt_dlp
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from src.scrapers.primary_scraper import PrimaryScraper, FatalScraperError 
# Moved to inside scan_videos to prevent startup hang
from src.page_archiver import archive_page
from src.media_library import MediaLibrary
from src.manifest_manager import ManifestManager
from src.reporter import print_detailed_statistics

STORAGE_DIR = ".storage"
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
OUTPUT_DIR = "downloads"
FAILED_LOG = os.path.join(STORAGE_DIR, "failed_downloads.txt")

# Initialize Manager
manifest_mgr = ManifestManager(storage_dir=STORAGE_DIR, manifest_filename="downloaded_video.txt")

def scan_videos(limit=None, update_metadata=False, offset=0, verbose=False):
    print(f"🚀 Starting Phased Scan... (Offset: {offset})")
    
    # Lazy Import to prevent startup hang
    try:
        from src.scrapers.primary_scraper import PrimaryScraper, FatalScraperError
    except ImportError as e:
        print(f"❌ Failed to import Scraper: {e}")
        return

    collected_lessons = []
    
    # --- PHASE 1: STRUCTURE DISCOVERY ---
    try:
        scraper = PrimaryScraper()
        scraper.scan_structure(verbose=verbose)
    except FatalScraperError as e:
        print(f"\n🛑 Structure Scan Failed: {e}")
        return
    except Exception as e:
        print(f"\n❌ Unexpected Error in Phase 1: {e}")
        return

    # --- PHASE 2: CONTENT EXTRACTION ---
    print("\n" + "-"*50)
    print("📥 Starting Content Extraction (Phase 2)...")
    print("-"*50)
    
    try:
        def on_lesson_hydrated(lesson_data):
            # 1. Archive
            archive_page(lesson_data['course_url'], lesson_data.get('title', 'Untitled'))
            
            # 2. Metadata Database Update
            video_url = lesson_data.get('url')
            try:
                 content_data = {}
                 if os.path.exists(CONTENT_FILE):
                     with open(CONTENT_FILE, "r", encoding="utf-8") as f:
                         try: content_data = json.load(f)
                         except: pass
                 
                 content_data[lesson_data['course_url']] = {
                     "title": lesson_data.get('title'),
                     "video_url": video_url,
                     "description": lesson_data.get('description'),
                     "links": lesson_data.get('links'),
                     "archived": True
                 }
                 with open(CONTENT_FILE, "w", encoding="utf-8") as f:
                     json.dump(content_data, f, indent=2, ensure_ascii=False)
            except: pass

            collected_lessons.append(lesson_data)
            
            # Incremental Save
            if len(collected_lessons) % 5 == 0:
                 manifest_mgr.save_manifest(collected_lessons)

        # Execute Extraction
        collected_lessons = scraper.scan_content(limit=limit, offset=offset, callback=on_lesson_hydrated)
        
    except FatalScraperError as e:
        print(f"\n🛑 Content Scan Stopped: {e}")
    except Exception as e:
        print(f"\n❌ Error in Phase 2: {e}")
    
    # Final Save
    if collected_lessons:
        manifest_mgr.save_manifest(collected_lessons)
                
    # Scan Summary
    print_detailed_statistics(collected_lessons)
    
    print("\n" + "="*50)
    print(f"📄  Manifest File: {os.path.abspath(MANIFEST_FILE)}")
    print("="*50)
    print(f"👉 Next Step: Review the manifest file, then run:")
    print(f"   ./download.sh")
    print("="*50 + "\n")

def download_videos(force=False):
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest file '{MANIFEST_FILE}' not found. Run with --scan first.")
        return

    if not os.path.exists(OUTPUT_DIR):
        try: os.makedirs(OUTPUT_DIR)
        except OSError as e:
            print(f"❌ Error creating output dir: {e}")
            return

    print(f"📂 Loading manifest: {MANIFEST_FILE}")
    videos_to_download = []
    
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3: continue
            
            index_str = parts[0]
            url = parts[2]
            title = parts[1]
            course = parts[3] if len(parts) > 3 else "Unknown Course"
            section = parts[4] if len(parts) > 4 else "General"
            
            if not url.startswith("http"): continue

            videos_to_download.append({
                "index": index_str,
                "title": title,
                "url": url,
                "course": course,
                "section": section
            })

    total_videos = len(videos_to_download)
    print(f"⬇️ Queued {total_videos} videos for download to {OUTPUT_DIR}")

    if total_videos == 0:
        print("No videos to download.")
        return

    # Initialize Media Library
    media_lib = MediaLibrary()
    media_lib.build_index()

    success_count = 0
    fail_count = 0
    failed_items = []
    max_workers = 3

    with tqdm(total=total_videos, desc="Overall Progress", unit="file") as total_pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for vid in videos_to_download:
                pbar = tqdm(total=100, desc=f"{vid['index']} {vid['title'][:15]}...", unit="MB", leave=False)
                future = executor.submit(
                        _download_single, 
                        vid['url'], 
                        vid['title'], 
                        vid['index'],
                        vid.get('course', 'Unknown'),
                        vid.get('section', 'General'),
                        pbar,
                        force,
                        media_lib
                    )
                futures[future] = vid

            for future in concurrent.futures.as_completed(futures):
                vid = futures[future]
                try:
                    res = future.result()
                    if res:
                         success_count += 1
                         manifest_mgr.mark_video_completed(vid['index'])
                    else:
                         fail_count += 1
                         failed_items.append(vid)
                except:
                    fail_count += 1
                    failed_items.append(vid)
    
    print("\n" + "="*50)
    print(f"🎉  Download Batch Finished!")
    print(f"✅  Successful: {success_count}/{total_videos}")
    
    if failed_items:
        print(f"❌  Failed: {len(failed_items)}")
        with open(FAILED_LOG, "w", encoding="utf-8") as f:
            f.write("# Failed Downloads List\n")
            for item in failed_items:
                f.write(f"{item['index']} | {item['title']} | {item['url']}\n")
        print(f"\n📂  Failed list saved to: {FAILED_LOG}")
            
    print(f"📂  Location: {os.path.abspath(OUTPUT_DIR)}")
    print("="*50)

def _sanitize_folder_name(name):
    import re
    sanitized = re.sub(r'[^\w\s\-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized[:60]

def _download_single(video_url, title, index_str, course, section, pbar, force=False, media_lib=None):
    # 1. Start Smart Skip (Library Check)
    if media_lib and not force:
        existing_path = media_lib.find_file(title)
        if existing_path and os.path.exists(existing_path) and os.path.getsize(existing_path) > 0:
             tqdm.write(f"   ✨ Found in library: {os.path.basename(existing_path)}")
             pbar.update(100)
             pbar.close()
             return True
    
    # 2. Output Path Prep
    course_dir = os.path.join(OUTPUT_DIR, _sanitize_folder_name(course))
    section_dir = os.path.join(course_dir, _sanitize_folder_name(section))
    
    try: os.makedirs(section_dir, exist_ok=True)
    except: return False
    
    safe_title = title.replace("/", "_").replace("\\", "_")
    filename = f"{index_str}_{safe_title}.mp4"
    output_path = os.path.join(section_dir, filename)
    
    # 3. Check Local Existence
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0 and not force:
        pbar.update(100)
        pbar.close()
        return True

    # 4. Download
    ydl_opts = {
        "outtmpl": output_path,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: _update_progress(d, pbar)],
        "quiet": True,
        "no_warnings": True,
        "overwrites": force,
        "retries": 10
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return True
    except Exception as e:
        tqdm.write(f"\n❌ Error {filename}: {e}")
        return False
    finally:
        pbar.close()

def _update_progress(d, pbar):
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        if total > 0:
            percentage = (downloaded / total) * 100
            pbar.n = int(percentage)
            pbar.refresh()
    elif d['status'] == 'finished':
        pbar.n = 100
        pbar.refresh()

def archive_manifest_pages():
    if not os.path.exists(MANIFEST_FILE): return
    urls = []
    with open(MANIFEST_FILE, 'r') as f:
        for line in f:
            if '|' in line and not line.strip().startswith('#'):
                parts = line.split('|')
                if len(parts) >= 3: urls.append({'url': parts[2].strip(), 'title': parts[1].strip()})
    
    print(f"📋 Archiving {len(urls)} pages...")
    for item in urls:
        archive_page(item['url'], item['title'])

def main():
    parser = argparse.ArgumentParser(description="Modular Smart Scraper")
    parser.add_argument("--scan", action="store_true", help="Scan site and update manifest")
    parser.add_argument("--download", action="store_true", help="Download videos from manifest")
    parser.add_argument("--archive", action="store_true", help="Archive full HTML/Assets")
    parser.add_argument("--force", action="store_true", help="Force download")
    parser.add_argument("--limit", type=int, help="Limit number of videos")
    parser.add_argument("--update-metadata", action="store_true", help="Rescan URLs")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--offset", type=int, default=0, help="Start offset")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode")
    
    args = parser.parse_args()
    
    if args.visible: os.environ["HEADLESS_MODE"] = "false"
    
    if args.scan:
        scan_videos(limit=args.limit, update_metadata=args.update_metadata, offset=args.offset, verbose=args.verbose)
    elif args.download:
        download_videos(force=args.force)
    elif args.archive:
        archive_manifest_pages()
    else:
        print("🤖 Modular Scraper Mode")
        print("1. 🔍 Scan")
        print("2. ⬇️ Download")
        choice = input("Select option (1/2): ").strip()
        if choice == "1": scan_videos(verbose=True)
        elif choice == "2": download_videos()

if __name__ == "__main__":
    main()
