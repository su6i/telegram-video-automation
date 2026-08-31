import os
import sys
import argparse
import concurrent.futures
from tqdm import tqdm
import yt_dlp
import json
import re

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# from src.scrapers.primary_scraper import PrimaryScraper, FatalScraperError 
# Moved to inside scan_videos to prevent startup hang
from src.page_archiver import archive_page
from src.media_library import MediaLibrary
# from src.manifest_manager import ManifestManager # Can't use global import if it needs dynamic paths? 
# Actually we can pass paths to ManifestManager

from src import config

# Dynamic Configuration
STORAGE_DIR = config.get_path("base_dir")
CONTENT_FILE = config.get_path("content_file")
MANIFEST_FILE = config.get_path("manifest_file")
OUTPUT_DIR = config.get_path("downloads_dir")
FAILED_LOG = config.get_path("failed_log")

# Initialize Manager (Import after config load)
from src.manifest_manager import ManifestManager
manifest_mgr = ManifestManager(storage_dir=STORAGE_DIR, manifest_filename=os.path.basename(MANIFEST_FILE))

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
            # If verbose, save EVERY time for debugging. Else save every 5.
            save_interval = 1 if verbose else 5
            
            if len(collected_lessons) % save_interval == 0:
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
    
    current_course = "Unknown Course"
    current_section = "General"
    
    # Regex to parse 'Index_Title' (supports '001_Title' and '039_1_Title')
    index_title_pattern = re.compile(r"^(\d+(?:_\d+)?)_(.*)$")

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            # Context Tracking
            if line.startswith("# === "):
                current_course = line.replace("# === ", "").replace(" ===", "").strip()
                current_section = "General" # Reset section on new course
                continue
            if line.startswith("## --- "):
                current_section = line.replace("## --- ", "").replace(" ---", "").strip()
                continue
            if line.startswith("#"): continue
            
            parts = [p.strip() for p in line.split("|")]
            
            parts = [p.strip() for p in line.split("|")]
            
            # --- Smart Parse: Find URL ---
            url_idx = -1
            for i, p in enumerate(parts):
                if p.startswith("http"):
                    url_idx = i
                    break
            
            if url_idx == -1: continue # No URL found
            
            url = parts[url_idx]
            
            # --- Extract Metadata (Course/Section) ---
            # Default to context
            vid_course = current_course
            vid_section = current_section
            
            # If explicit columns exist AFTER the URL
            if len(parts) > url_idx + 1:
                vid_course = parts[url_idx+1]
            if len(parts) > url_idx + 2:
                vid_section = parts[url_idx+2]

            # --- Extract Index & Title ---
            # Everything BEFORE the URL
            pre_url_parts = parts[:url_idx]
            
            index_str = "999"
            title = "Unknown"
            
            if pre_url_parts:
                first = pre_url_parts[0]
                # Check for pure index: "001" or "039_4"
                if re.match(r"^\d+(?:_\d+)?$", first) and len(pre_url_parts) > 1:
                    # Format: Index | Title
                    index_str = first
                    title = " - ".join(pre_url_parts[1:])
                else:
                    # Format: Index_Title (or just Title)
                    # Try to split Index_Title
                    match = index_title_pattern.match(first)
                    if match:
                        index_str = match.group(1)
                        t_prefix = match.group(2)
                        # Append any other cols (e.g. Index_Prefix | Suffix)
                        if len(pre_url_parts) > 1:
                            title = t_prefix + " - " + " - ".join(pre_url_parts[1:])
                        else:
                            title = t_prefix
                    else:
                        # Fallback: No index found in first part
                        # e.g. "Just a Title"
                        title = " - ".join(pre_url_parts)

            videos_to_download.append({
                "index": index_str,
                "title": title,
                "url": url,
                "course": vid_course,
                "section": vid_section
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

def calculate_next_index(manifest_path, course, section):
    """
    Calculates the next appropriate index for a video in a specific section.
    Returns something like '039_X' or a new sequential number.
    """
    if not os.path.exists(manifest_path): return "001"
    
    last_index_in_section = None
    max_global_index = 0
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        for line in f:
            if "|" not in line or line.strip().startswith("#"): continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5: continue
            
            idx = parts[0]
            c = parts[3]
            s = parts[4]
            
            # Global max tracker (for purely new sections)
            if idx.isdigit():
                 max_global_index = max(max_global_index, int(idx))
            
            # Match Course and Section
            if c == course and s == section:
                last_index_in_section = idx

    if last_index_in_section:
        # If last index was '039' or '039_3', we want next sub-index
        base = last_index_in_section.split("_")[0]
        if "_" in last_index_in_section:
            try:
                sub = int(last_index_in_section.split("_")[1])
                return f"{base}_{sub + 1}"
            except: return f"{base}_{1}"
        else:
            return f"{base}_1"
    else:
        # New section? Just increment global max
        return f"{max_global_index + 1:03d}"

def process_single_url(url, verbose=False, download=True):
    print(f"🔗 Processing Single URL: {url}")
    if not download:
        print("   🔍 Scan Mode: Metadata will be extracted and indexed, but NOT downloaded.")
    
    # Lazy Import
    try:
        from src.scrapers.primary_scraper import PrimaryScraper
    except ImportError as e:
        print(f"❌ Scraper import failed: {e}")
        import traceback
        traceback.print_exc()
        return

    scraper = PrimaryScraper()
    try:
        # 1. Get Details
        details = scraper.get_lesson_details(url)
    except Exception as e:
        print(f"❌ Failed to get details: {e}")
        return

    # Prepare Metadata
    title = details.get('title', 'Untitled')
    course = details.get('course_title', 'Unknown Course')
    section = details.get('section', 'General')
    video_url = details.get('url')
    
    print(f"   📘 Course: {course}")
    print(f"   📂 Section: {section}")
    print(f"   📝 Title: {title}")
    
    # --- Interactive Metadata Correction ---
    if section == "General":
        print(f"   ⚠️  Section detection defaulted to 'General'.")
        user_sec = input(f"   ✍️  Enter correct Section name (or Press Enter to keep '{section}'): ").strip()
        if user_sec:
            section = user_sec
            details['section'] = section # Update details dict for metadata.json

    # Calculate Index based on (potentially new) section
    suggested_index = calculate_next_index(MANIFEST_FILE, course, section)
    print(f"   🔢 Proposed Index: {suggested_index}")
    
    user_idx = input(f"   ✍️  Enter Index (or Press Enter to keep '{suggested_index}'): ").strip()
    if user_idx:
        index_str = user_idx
    else:
        index_str = suggested_index

    # 2. Update Manifest
    # CRITICAL: Use the extracted VIDEO URL (e.g. Wistia embed), not the page URL.
    manifest_url = video_url if video_url else url
    
    new_entry = {
         "index": index_str,
         "title": title,
         "url": manifest_url,
         "course": course,
         "section": section
    }
    insert_into_manifest(new_entry)
            
    print(f"   ✅ Final Metadata: [{index_str}] {course} > {section} > {title}")

    if download:
        # 3. Archive Page
        # We want to put it in downloads/Course/Section/Title_Page/
        sanitized_course = _sanitize_folder_name(course)
        sanitized_section = _sanitize_folder_name(section)
        sanitized_title = _sanitize_folder_name(title)
        
        target_base = os.path.join(OUTPUT_DIR, sanitized_course, sanitized_section)
        archive_dir = os.path.join(target_base, f"{sanitized_title}_Assets")
        
        print(f"   📦 Archiving to: {archive_dir}")
        archive_report = archive_page(url, title, output_dir=archive_dir)
        
        # Save Metadata
        if archive_report.get('success'):
             meta_file = os.path.join(archive_dir, "metadata_full.json")
             with open(meta_file, "w", encoding="utf-8") as f:
                 json.dump(details, f, indent=2, ensure_ascii=False)
            
        # 4. Download Video
        if video_url:
            print(f"   ⬇️ Downloading video...")
            # Mock pbar
            class MockPbar:
                def update(self, n): pass
                def close(self): pass
                def refresh(self): pass
                n = 0
                
            success = _download_single(
                video_url, 
                title, 
                index_str, 
                course, 
                section, 
                MockPbar(), 
                force=True
            )
            
            # Construct expected path manually to report it (since _download_single constructs it locally)
            safe_title_vid = title.replace("/", "_").replace("\\", "_")
            filename_vid = f"{index_str}_{safe_title_vid}.mp4"
            final_video_path = os.path.join(target_base, filename_vid)
            
            if success: 
                print("   ✅ Video Downloaded")
                print(f"   📂 Saved to: {os.path.abspath(final_video_path)}")
            
def insert_into_manifest(entry_data):
    """
    Inserts a video entry into the manifest file at the correct location.
    entry_data: {index, title, url, course, section}
    """
    if not os.path.exists(MANIFEST_FILE):
        return False

    lines = []
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    course = entry_data['course']
    section = entry_data['section']
    
    # FORMAT CORRECTION: Matches '001_Title | URL' (2 columns)
    # Removing extra columns (Course replacement/Section) to stay compliant with file history
    clean_title = entry_data['title'].replace("|", "-").strip()
    # Ensure Index_Title
    full_label = f"{entry_data['index']}_{clean_title}"
    new_line = f"{full_label} | {entry_data['url']}\n"
    
    # Logic to find insertion point
    course_found = False
    section_found = False
    insertion_idx = -1
    
    for i, line in enumerate(lines):
        # 1. Find Course Header
        if line.strip().startswith(f"# === {course}"):
            course_found = True
        
        # 2. Find Section Header (only if course currently active or global search if simple structure)
        if course_found or True: # Simplified structure assumption standard
             if line.strip().startswith(f"## --- {section} ---"):
                 section_found = True
                 insertion_idx = i + 1 # Start looking after header
                 
                 # Fast forward to end of this section (before next section or course)
                 for j in range(i + 1, len(lines)):
                     line_s = lines[j].strip()
                     if line_s.startswith("## ---") or line_s.startswith("# ===") or line_s.startswith("# ----------------"):
                         insertion_idx = j
                         break
                     else:
                         insertion_idx = j + 1 # Keep pushing down
                 break
    
    if insertion_idx != -1:
        lines.insert(insertion_idx, new_line)
    else:
        # Append if structure not found
        lines.append(f"\n# === {course} ===\n")
        lines.append(f"\n## --- {section} ---\n")
        lines.append(new_line)
        
    try:
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"Write Error: {e}")
        return False

    # ... inside process_single_url after download ...
        if success: 
            print("   ✅ Video Downloaded")
            print(f"   📂 Saved to: {os.path.abspath(final_video_path)}")
            
            # 4. Update Manifest (Insert at correct location)
            entry = {
                'index': index_str,
                'title': title,
                'url': video_url,
                'course': course,
                'section': section
            }
            if insert_into_manifest(entry):
                print(f"   📝 Inserted into manifest: {MANIFEST_FILE}")
            else:
                print(f"   ⚠️ Failed to update manifest.")
                
        else: print("   ❌ Video Download Failed")
    else:
        print("   ⚠️ No video URL found.")


def main():
    parser = argparse.ArgumentParser(description="Modular Smart Scraper")
    parser.add_argument("--url", help="Process a single specific URL")
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
    
    if args.visible: os.environ["HEADLESS_MODE"] = "false"
    
    if args.url:
        process_single_url(args.url, verbose=args.verbose)
    elif args.scan:
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
