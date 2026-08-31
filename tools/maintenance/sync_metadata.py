
import os
import json
import re

STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
HISTORY_FILE = os.path.join(STORAGE_DIR, "upload_history.json")
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")

def parse_manifest():
    """Parses the manifest and returns a list of video objects."""
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest not found: {MANIFEST_FILE}")
        return []

    videos = []
    current_course = "Unknown Course"
    current_section = "General"

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue

            if line.startswith("# === "):
                current_course = line.replace("# === ", "").split(" ===")[0].split("(")[0].strip()
                current_section = "General"
            elif line.startswith("## --- "):
                current_section = line.replace("## --- ", "").replace(" ---", "").strip()
            elif "|" in line:
                is_done = line.startswith("# [DONE]")
                clean_line = line.replace("# [DONE]", "").strip()
                
                # Flexible parsing for Index | Title | URL or Index_Title | URL
                parts = [p.strip() for p in clean_line.split("|")]
                
                url = ""
                title = ""
                index = ""
                
                # Extract Index
                idx_match = re.match(r"^(\d{3})", parts[0])
                if not idx_match: continue
                index = idx_match.group(1)

                if len(parts) >= 3:
                    # Index | Title | URL
                    title = parts[1]
                    url = parts[2]
                elif len(parts) == 2:
                    # Index_Title | URL
                    url = parts[1]
                    title = parts[0][3:].strip("_ ")
                
                if url:
                    videos.append({
                        "index": index,
                        "title": title,
                        "url": url,
                        "course": current_course,
                        "section": current_section,
                        "is_done": is_done
                    })
    return videos

def sync():
    print("🔄 Starting Metadata Synchronization...")
    
    videos = parse_manifest()
    if not videos:
        return

    # Load History
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    # Load Content
    content = {}
    if os.path.exists(CONTENT_FILE):
        with open(CONTENT_FILE, "r", encoding="utf-8") as f:
            content = json.load(f)

    # 1. Map content by video_url for faster lookup
    video_to_lesson_map = {}
    for lesson_url, data in content.items():
        v_url = data.get('video_url') or lesson_url # Many entries use video_url as key now
        video_to_lesson_map[v_url] = lesson_url

    content_updated = 0
    history_updated = 0

    for v in videos:
        # --- SYNC CONTENT ---
        url = v['url']
        lesson_url = video_to_lesson_map.get(url)
        
        entry = None
        if url in content:
            entry = content[url]
        elif lesson_url and lesson_url in content:
            entry = content[lesson_url]
        
        if entry:
            # Update existing
            entry['title'] = v['title']
            entry['course_title'] = v['course']
            entry['section'] = v['section']
            # Ensure video_url exists
            if 'video_url' not in entry:
                entry['video_url'] = url
            content_updated += 1
        else:
            # Create new
            content[url] = {
                "title": v['title'],
                "video_url": url,
                "course_title": v['course'],
                "section": v['section'],
                "description": "",
                "links": []
            }
            content_updated += 1

        # --- SYNC HISTORY ---
        idx = v['index']
        if v['is_done']:
            if idx not in history:
                history[idx] = {
                    "title": v['title'],
                    "msg_id": 0,
                    "link": "manual_sync",
                    "type": "manual"
                }
                history_updated += 1
            else:
                # Update title in history if changed
                if history[idx].get('title') != v['title']:
                    history[idx]['title'] = v['title']
                    history_updated += 1

    # Save
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    
    with open(CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)

    print(f"✅ Sync Complete!")
    print(f"   📝 Updated {content_updated} entries in scraped_content.json")
    print(f"   📜 Updated {history_updated} entries in upload_history.json")

if __name__ == "__main__":
    sync()
