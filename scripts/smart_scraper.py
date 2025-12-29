
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

import json

# Storage directory
STORAGE_DIR = ".storage"
os.makedirs(STORAGE_DIR, exist_ok=True)
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")
OUTPUT_DIR = "downloads"

print_lock = threading.Lock()
manifest_lock = threading.Lock()

def _mark_video_completed(index_str):
    """Marks a video as completed in the manifest file by commenting it out."""
    with manifest_lock:
        try:
            lines = []
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.strip().startswith(f"{index_str} |"):
                        # Mark as done
                        f.write(f"# [DONE] {line}")
                        print(f"   📝 Marked {index_str} as done in manifest.")
                    else:
                        f.write(line)
        except Exception as e:
            print(f"   ❌ Error marking video as done: {e}")

def _save_manifest(videos, limit=None):
    from itertools import groupby
    
    # 1. Deduplicate while preserving order from the fresh scan
    seen_urls = set()
    fresh_videos_map = {}
    for v in videos:
        # Normalize Key
        n_url = v['url'].strip().rstrip("/")
        if n_url not in seen_urls:
            seen_urls.add(n_url)
            fresh_videos_map[n_url] = v
    
    # 2. Load EXISTING manifest
    # We will rebuild the list of all videos. 
    # If a video is in the fresh scan, we use the FRESH data (rich metadata) but keep the OLD index/status.
    # If it's not in the fresh scan, we keep the OLD data.
    # If it's new, we add it.
    
    # If it's not in the fresh scan, we keep the OLD data.
    # If it's new, we add it.
    
    final_videos = []
    processed_urls = set()
    
    def _norm_url(u):
        return u.strip().rstrip("/")

    max_index = 0
    
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("# Index"): 
                        continue
                    
                    # Check for [DONE]
                    is_done = "# [DONE]" in line
                    
                    # Remove comments for parsing
                    clean_line = line.replace("# [DONE]", "").strip()
                    if clean_line.startswith("#"): # Skip headers/comments
                         continue
                        
                    if "|" in clean_line:
                        parts = [p.strip() for p in clean_line.split("|")]
                        if len(parts) >= 3:
                            idx_str = parts[0]
                            title = parts[1]
                            url = parts[2]
                            course = parts[3] if len(parts) > 3 else 'Unknown'
                            section = parts[4] if len(parts) > 4 else 'General'
                            
                            if not url.startswith("http"): continue
                            
                            # Track max index
                            if idx_str.isdigit():
                                max_index = max(max_index, int(idx_str))
                            
                            
                            # Normalize URL
                            norm_url = _norm_url(url)
                            processed_urls.add(norm_url)
                            
                            # Merge logic
                            vid_data = {
                                'index': idx_str,
                                'url': url, # Keep original
                                'is_done': is_done,
                                'title': title, # Default to old title
                                'course_title': course,
                                'section': section,
                                'category': section, # Fallback for old records
                                'subsection': None
                            }
                            
                            # If we have FRESH data for this URL, upgrade the metadata
                            if norm_url in fresh_videos_map:
                                fresh = fresh_videos_map[norm_url] # Keyed by norm_url? No, fresh map needs fix too.
                                vid_data['title'] = fresh.get('title', title)
                                vid_data['course_title'] = fresh.get('course_title', course)
                                vid_data['section'] = fresh.get('section', section) # Specific
                                vid_data['category'] = fresh.get('category', section)
                                vid_data['subsection'] = fresh.get('subsection', None)
                            
                            final_videos.append(vid_data)
        except Exception as e:
            print(f"⚠️ Could not read existing manifest: {e}")
            
    # 3. Add NEW videos from fresh scan
    # Sort fresh videos by their appearance order in the scan
    # (The `videos` list passed in is presumably in correct order)
    
    new_found = []
    for v in videos:
        n_url = v['url'].strip().rstrip("/")
        if n_url not in processed_urls:
            # It's a new video
            v_data = {
                'index': None, # Will assign later
                'url': v['url'],
                'is_done': False,
                'title': v.get('title', 'Unknown'),
                'course_title': v.get('course_title', 'Unknown Course'),
                'section': v.get('section', 'General'),
                'category': v.get('category', 'General'),
                'subsection': v.get('subsection', None)
            }
            new_found.append(v_data)
            processed_urls.add(v['url'])
    
    # Append new videos
    final_videos.extend(new_found)
    
    # 4. Renumber logic
    # We should preserve indices of existing videos if possible, but the user wants rigorous ordering.
    # If we renumber, we break consistency with downloaded files.
    # Strategy: Renumber everything based on the Sort Order (Course -> Category -> Subsection).
    # This is what the user implies by "Corrections".
    
    # Sort for consistent manifest
    # Key: Course -> Category -> (Subsection/Index?)
    # Since we can't easily sort by "Scan Order" unless we preserved it. 
    # We'll rely on the order in `final_videos` roughly, but we should group them.
    
    # Let's simple-sort by Course -> Category -> Section
    # But this might mess up the lesson order WITHIN a module if we don't have track numbers.
    # The scan order (in `videos`) is usually the correct lesson order.
    # Existing manifest order is also usually correct.
    # New videos are appended.
    # So `final_videos` IS the correct order (Existing + New).
    
    # Re-assign indices sequentially
    for idx, v in enumerate(final_videos, 1):
        v['index'] = f"{idx:03d}"
    
    # 5. Write Manifest
    with manifest_lock:
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            f.write(f"# Index | Title | URL | Course | Section | Status\n")
            f.write(f"# To skip a video, delete the line or put a '#' at the start\n")
            
            # Group by Course
            # Use itertools.groupby but needs sorted input by key
            # We want to preserve list order, but group by Course
            
            current_course = None
            current_category = None
            current_subsection_header = None # Tracks the typed ### header
            
            # Helper to get course/cat
            for v in final_videos:
                c_title = v['course_title']
                cat = v.get('category', v['section'])
                sub = v.get('subsection')
                sec_name = v['section'] # This is the "Folder Name" (most specific)
                
                # LEVEL 1: Course
                if c_title != current_course:
                    current_course = c_title
                    # Count videos in this course
                    count = sum(1 for x in final_videos if x['course_title'] == c_title)
                    f.write(f"\n# === {c_title} ({count} videos) ===\n")
                    current_category = None # Reset category
                    current_subsection_header = None
                
                # LEVEL 2: Category (##)
                # If we have a category, use it. If not, use section.
                actual_cat = cat if cat else sec_name
                
                if actual_cat != current_category:
                    f.write(f"\n## --- {actual_cat} ---\n")
                    current_category = actual_cat
                    current_subsection_header = None
                
                # LEVEL 3: Sub-section (###)
                # Only if subsection is present and DISTINCT from category
                if sub and sub != actual_cat:
                    if sub != current_subsection_header:
                        f.write(f"### {sub}\n")
                        current_subsection_header = sub
                
                # Write Line
                # We use 'sec_name' (v['section']) for the Section Column to ensure unique folders if needed
                status_pfx = "# [DONE] " if v.get('is_done') else ""
                line = f"{v['index']} | {v['title']} | {v['url']} | {c_title} | {sec_name}"
                f.write(f"{status_pfx}{line}\n")



def _sanitize_path(name):
    """Convert text to valid folder name."""
    import re
    sanitized = re.sub(r'[^\w\s\-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized[:60].strip('_')

def _archive_lesson(lesson_data):
    """Archives lesson content (text, html, attachments) to .storage/course_archive/"""
    try:
        import os
        
        course = _sanitize_path(lesson_data.get('course_title', 'Unknown Course'))
        section = _sanitize_path(lesson_data.get('section', 'General'))
        title = _sanitize_path(lesson_data.get('title', 'Untitled Lesson'))
        
        archive_root = os.path.join(STORAGE_DIR, "course_archive")
        lesson_dir = os.path.join(archive_root, course, section, title)
        os.makedirs(lesson_dir, exist_ok=True)
        
        # 1. Save content.txt
        with open(os.path.join(lesson_dir, "content.txt"), "w", encoding="utf-8") as f:
            f.write(f"TITLE: {lesson_data['title']}\n")
            f.write(f"URL: {lesson_data['course_url']}\n")
            f.write(f"VIDEO: {lesson_data.get('url', 'None')}\n")
            f.write("-" * 40 + "\n\n")
            f.write(lesson_data.get('description', ''))
            
        # 2. Save page_source.html
        if lesson_data.get('html'):
            with open(os.path.join(lesson_dir, "page_source.html"), "w", encoding="utf-8") as f:
                f.write(lesson_data['html'])
                
        # 3. Download Attachments
        links = lesson_data.get('links', [])
        if links:
            attach_dir = os.path.join(lesson_dir, "attachments")
            for link in links:
                url = link['url']
                # Heuristic: If it looks like a file download
                if any(ext in url.lower() for ext in ['.pdf', '.zip', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.mp3']):
                    os.makedirs(attach_dir, exist_ok=True)
                    _download_attachment(url, attach_dir, link.get('text'))
                    
    except Exception as e:
        print(f"   ⚠️ Archiving Error for {lesson_data['title']}: {e}")

def _download_attachment(url, dest_dir, text_label=None):
    from urllib import request as urllib_request
    try:
        # Extract filename
        fname = url.split("/")[-1].split("?")[0]
        if not fname or len(fname) < 3:
            if text_label:
                fname = _sanitize_path(text_label) + ".unknown"
            else:
                return

        path = os.path.join(dest_dir, fname)
        if os.path.exists(path): return
        
        print(f"       📩 Archiving attachment: {fname}")
        
        # Add a User-Agent to avoid 403s
        opener = urllib_request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')]
        urllib_request.install_opener(opener)
        
        urllib_request.urlretrieve(url, path)
    except Exception as e:
        print(f"       ❌ Failed to download attachment {url}: {e}")

def scan_videos(limit=None, update_metadata=False):
    print("🔍 Scanning site for ALL content (Videos & Documents)...")
    
    # Load existing URLs to avoid re-scanning
    existing_urls = set()
    if os.path.exists(MANIFEST_FILE):
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and line[0].isdigit() and '|' in line:
                        parts = line.split('|')
                        if len(parts) > 2:
                            url = parts[2].strip()
                            if url:
                                existing_urls.add(url)
        except:
            pass
    
    collected_lessons = []
    new_items_count = 0
    
    def on_lesson_found(lesson_data):
        nonlocal new_items_count
        lesson_url = lesson_data.get('course_url')
        video_url = lesson_data.get('url')
        
        # 1. ALWAYS Archive EVERYTHING during scan
        _archive_lesson(lesson_data)
        
        # 2. Metadata Database Update
        try:
             content_data = {}
             if os.path.exists(CONTENT_FILE):
                 with open(CONTENT_FILE, "r", encoding="utf-8") as f:
                     try: content_data = json.load(f)
                     except: pass
             
             content_data[lesson_url] = {
                 "title": lesson_data.get('title'),
                 "video_url": video_url,
                 "description": lesson_data.get('description'),
                 "links": lesson_data.get('links'),
                 "archived": True
             }
             with open(CONTENT_FILE, "w", encoding="utf-8") as f:
                 json.dump(content_data, f, indent=2, ensure_ascii=False)
        except: pass

        # 3. Manifest Update (Only if it's a NEW video)
        if video_url and video_url not in existing_urls:
            collected_lessons.append(lesson_data)
            new_items_count += 1

        # Incremental manifest save
        if new_items_count > 0 and new_items_count % 5 == 0:
            _save_manifest(collected_lessons)
            
    scraper = PrimaryScraper()
    scraper.get_video_links(limit=limit, callback=on_lesson_found)
    
    # Final Manifest Save
    if collected_lessons:
        _save_manifest(collected_lessons)
                
    # Scan Summary
    print("\n" + "="*50)
    print(f"🚀  Scan Completed Successfully!")
    print(f"📼  Total Videos Found: {len(collected_videos)}")
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
            
            # Parse line "001 | Title | URL | Course | Section"
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            
            index_str = parts[0]
            url = parts[2]  # URL is 3rd part now (after Title)
            title = parts[1]  # Title is 2nd part
            course = parts[3] if len(parts) > 3 else "Unknown Course"
            section = parts[4] if len(parts) > 4 else "General"
            
            if not url.startswith("http"):
                 print(f"⚠️ Skipping invalid line (No URL): {line}")
                 continue

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

    success_count = 0
    fail_count = 0

    max_workers = 3
    failed_items = []

    # Initialize Media Library
    media_lib = MediaLibrary()
    media_lib.build_index()

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
                        media_lib  # Pass the library
                    )
                futures[future] = vid

            # Wait for all and count results
            for future in concurrent.futures.as_completed(futures):
                vid = futures[future]
                try:
                    res = future.result()
                    if res:
                         success_count += 1
                         # Mark as done in manifest immediately
                         _mark_video_completed(vid['index'])
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
        failed_log = os.path.join(STORAGE_DIR, "failed_downloads.txt")
        with open(failed_log, "w", encoding="utf-8") as f:
            f.write("# Failed Downloads List\n")
            for item in failed_items:
                line = f"{item['index']} | {item['title']} | {item['url']}"
                f.write(f"{line}\n")
                print(f"   ⚠️ Failed: {item['index']} - {item['title']}")
        
        print(f"\n📂  Failed list saved to: {failed_log}")
            
    print(f"📂  Location: {os.path.abspath(OUTPUT_DIR)}")
    print("="*50)
    print("👉 To open downloads folder, run:")
    print(f"   open '{OUTPUT_DIR}'")
    print("="*50 + "\n")

MEDIA_PATHS_FILE = os.path.join(STORAGE_DIR, "media_paths.json")

def _normalize_title(filename):
    """
    Normalize filename for fuzzy matching.
    Removes leading index numbers (001_), extension, and special chars.
    """
    import re
    # Remove extension
    name = os.path.splitext(filename)[0]
    
    # Remove leading numbers/hyphens/underscores pattern (e.g. "001_", "01 - ", "1.")
    # Match start of string, digit+, and separator
    name = re.sub(r'^\d+[\s\-\_\.]+', '', name)
    
    # Lowercase and remove non-alphanumeric (keep only simple chars for comparison)
    # This helps match "Intro to AI" with "intro_to_ai"
    clean = re.sub(r'[^a-z0-9]', '', name.lower())
    return clean

class MediaLibrary:
    def __init__(self):
        self.index = {} # normalized_title -> full_path
        self.paths = []
        self._load_paths()
        
    def _load_paths(self):
        if not os.path.exists(MEDIA_PATHS_FILE):
             return
        
        try:
            with open(MEDIA_PATHS_FILE, 'r') as f:
                data = json.load(f)
                self.paths = data.get('paths', [])
                print(f"📂 Found {len(self.paths)} external media paths to scan.")
        except Exception as e:
            print(f"⚠️ Error reading media_paths.json: {e}")

    def build_index(self):
        if not self.paths:
            return
            
        print("🔍 Scanning external media paths for existing files...")
        count = 0
        for path in self.paths:
            # Resolve relative paths
            if not path.startswith("/"):
                path = os.path.abspath(os.path.join(os.getcwd(), path))
            
            if not os.path.exists(path):
                print(f"   ⚠️ Path not found: {path}")
                continue
                
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith(('.mp4', '.mov', '.mkv')):
                        norm = _normalize_title(file)
                        if norm:
                            self.index[norm] = os.path.join(root, file)
                            count += 1
        print(f"✅ Indexed {count} existing videos from media library.")

    def find_file(self, title):
        """Check if video title exists in index."""
        # Normalize the requested title (which usually comes from manifest without index prefix if it's just the title col)
        # But wait, manifest Title column is "Intro to AI", filename is "005_Intro_to_AI.mp4"
        # So we normalize the input title similar to how we normalized the filename
        norm = _normalize_title(title)
        return self.index.get(norm)

def _sanitize_folder_name(name):
    """Convert text to valid folder name."""
    # Remove special characters, keep alphanumeric, spaces, hyphens
    import re
    sanitized = re.sub(r'[^\w\s\-]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized[:60]  # Limit length

def _download_single(video_url, title, index_str, course, section, pbar, force=False, media_lib=None):
    # Returns True if success, False if error
    # Create folder structure: downloads/Course_Name/Section_Name/
    
    # 1. Check Media Library First (Smart Skip)
    if media_lib and not force:
        existing_path = media_lib.find_file(title)
        if existing_path:
             with print_lock:
                 # Verify size > 0
                 if os.path.getsize(existing_path) > 0:
                     tqdm.write(f"   ✨ Found in library: {os.path.basename(existing_path)}")
                     pbar.update(100)
                     pbar.close()
                     return True
    
    course_folder = _sanitize_folder_name(course)
    section_folder = _sanitize_folder_name(section)
    
    # Create nested folder structure
    course_dir = os.path.join(OUTPUT_DIR, course_folder)
    section_dir = os.path.join(course_dir, section_folder)
    
    try:
        os.makedirs(section_dir, exist_ok=True)
    except OSError as e:
        with print_lock:
            print(f"\n❌ Error creating folder: {e}")
        pbar.close()
        return False
    
    # Sanitize title for filename
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, "_")
    
    filename = f"{index_str}_{title}.mp4"
    output_path = os.path.join(section_dir, filename)
    
    # Skip if exists AND not forced AND has content
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0 and not force:
        with print_lock:
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
    parser.add_argument("--update-metadata", action="store_true", help="Rescan URLs even if they exist in manifest (for description updates)")
    
    args = parser.parse_args()
    
    if args.scan:
        scan_videos(limit=args.limit, update_metadata=args.update_metadata)
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
