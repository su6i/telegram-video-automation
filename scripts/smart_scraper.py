
import os
import sys
import argparse
import threading
import concurrent.futures
from tqdm import tqdm
import yt_dlp

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.primary_scraper import PrimaryScraper

MANIFEST_FILE = "video_manifest.txt"
MANIFEST_FILE = "video_manifest.txt"
OUTPUT_DIR = "downloads"

print_lock = threading.Lock()

def _save_manifest(videos, limit=None):
    from itertools import groupby
    
    # Sort first by course_title to ensure groupby works
    # We assume 'course_title' is in video dict. If not, fallback to 'Unknown Course'
    videos.sort(key=lambda x: x.get('course_title', 'Unknown Course'))
    
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Index | Title | URL | Status (Edit this file to filter)\n")
        f.write(f"# To skip a video, delete the line or put a '#' at the start\n")
        
        idx = 1
        for course_title, course_videos in groupby(videos, key=lambda x: x.get('course_title', 'Unknown Course')):
            course_videos_list = list(course_videos)
            count = len(course_videos_list)
            
            # Get total lessons count from the first video metadata if available
            total_lessons = course_videos_list[0].get('total_course_lessons', count)
            
            if limit and count < total_lessons:
                header = f"\n# === {course_title} (limit {count} of {total_lessons} videos) ===\n"
            else:
                 header = f"\n# === {course_title} ({count} videos) ===\n"

            f.write(header)
            
            current_section = None
            
            for v in course_videos_list:
                # Check for section change
                vid_section = v.get('section', 'General')
                if vid_section != current_section and vid_section != "General":
                    f.write(f"\n## --- {vid_section} ---\n")
                    current_section = vid_section
                
                # Format: Index | Section | Title | URL
                # This ensures the section becomes part of the filename during download (e.g. 001_Section - Title.mp4)
                if vid_section and vid_section != "General":
                    f.write(f"{idx:03d} | {vid_section} | {v['title']} | {v['url']}\n")
                else:
                    f.write(f"{idx:03d} | {v['title']} | {v['url']}\n")
                
                idx += 1

def scan_videos(limit=None):
    print("🔍 Scanning for videos... (This retrieves links but does NOT download)")
    
    collected_videos = []
    
    def on_video_found(video_data):
        collected_videos.append(video_data)
        # Incremental save every 5 videos
        if len(collected_videos) % 5 == 0:
            print(f"   💾 Saving progress... ({len(collected_videos)} videos)")
            _save_manifest(collected_videos, limit)
            
    scraper = PrimaryScraper()
    # Pass the callback to the scraper
    scraper.get_video_links(limit=limit, callback=on_video_found)
    
    if not collected_videos:
        print("❌ No videos found.")
        return

    print(f"✅ Found {len(collected_videos)} videos.")
    
    # Final Save
    _save_manifest(collected_videos, limit)
                
    # Scan Summary
    print("\n" + "="*50)
    print(f"🚀  Scan Completed Successfully!")
    print(f"📼  Total Videos Found: {len(collected_videos)}")
    print(f"📄  Manifest File: {os.path.abspath(MANIFEST_FILE)}")
    print("="*50)
    print(f"👉 Next Step: Review the manifest file, then run:")
    print(f"   ./run_smart.sh --download")
    print("="*50 + "\n")

def download_videos(force=False):
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest file '{MANIFEST_FILE}' not found. Run with --scan first.")
        return

    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
        except OSError as e:
            print(f"❌ Error creating output dir: {e}")
            return

    print(f"📂 Loading manifest: {MANIFEST_FILE}")
    videos_to_download = []
    
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Parse line "001 | Title | URL" -> Handle titles containing "|"
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            
            index_str = parts[0]
            url = parts[-1] # URL is always the last part
            title = " - ".join(parts[1:-1]) # Join all middle parts as title
            
            if not url.startswith("http"):
                 print(f"⚠️ Skipping invalid line (No URL): {line}")
                 continue

            videos_to_download.append({
                "index": index_str,
                "title": title,
                "url": url
            })

    total_videos = len(videos_to_download)
    print(f"⬇️ Queued {total_videos} videos for download to {OUTPUT_DIR}")

    if total_videos == 0:
        print("No videos to download.")
        return

    success_count = 0
    fail_count = 0

    max_workers = 3
    failed_items = []

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
                        pbar,
                        force
                    )
                futures[future] = vid

            # Wait for all and count results
            for future in concurrent.futures.as_completed(futures):
                vid = futures[future]
                try:
                    res = future.result()
                    if res:
                         success_count += 1
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
        
        # Save failed list
        failed_log = "failed_downloads.txt"
        with open(failed_log, "w", encoding="utf-8") as f:
            f.write("# Failed Downloads List\n")
            for item in failed_items:
                line = f"{item['index']} | {item['title']} | {item['url']}"
                f.write(f"{line}\n")
                print(f"   ⚠️ Failed: {item['index']} - {item['title']}")
        
        print(f"\n📂  Failed list saved to: {failed_log}")
            
    print(f"📂  Location: {OUTPUT_DIR}")
    print("="*50)
    print("👉 To open downloads folder, run:")
    print(f"   open '{OUTPUT_DIR}'")
    print("="*50 + "\n")

def _download_single(video_url, title, index_str, pbar, force=False):
    # Returns True if success, False if error
    # Sanitize title
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, "_")
    
    filename = f"{index_str}_{title}.mp4"
    output_path = os.path.join(OUTPUT_DIR, filename)
    
    # Skip if exists AND not forced AND has content
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0 and not force:
        with print_lock:
             # Just update progress if already exists
             pass
        pbar.update(100) # Finish bar
        pbar.close()
        return True # Considered success (already done)

    ydl_opts = {
        "outtmpl": output_path,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: _update_progress(d, pbar)],
        "quiet": True,
        "no_warnings": True,
        "overwrites": force,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return True
    except Exception as e:
        with print_lock:
            print(f"\n❌ Error {filename}: {e}")
        return False
    finally:
        pbar.update(100) # Ensure bar finishes
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

def main():
    parser = argparse.ArgumentParser(description="Content Creator Smart Scraper")
    parser.add_argument("--scan", action="store_true", help="Scan site and update manifest")
    parser.add_argument("--download", action="store_true", help="Download videos from manifest")
    parser.add_argument("--force", action="store_true", help="Force download even if file exists")
    parser.add_argument("--limit", type=int, help="Limit number of videos to scan (good for testing)")
    
    args = parser.parse_args()
    
    if args.scan:
        scan_videos(limit=args.limit)
    elif args.download:
        download_videos(force=args.force)
    else:
        # Interactive mode if no args
        print("🤖 Smart Scraper Mode")
        print("1. 🔍 Scan & Create Manifest")
        print("2. ⬇️ Download from Manifest")
        choice = input("Select option (1/2): ").strip()
        if choice == "1":
            scan_videos()
        elif choice == "2":
            download_videos() # Interactive default force=False
        else:
            print("Invalid toggle")

if __name__ == "__main__":
    main()
