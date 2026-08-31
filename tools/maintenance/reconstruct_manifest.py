
import json
import os
import re

CONTENT_FILE = ".storage/scraped_content.json"
MANIFEST_FILE = ".storage/downloaded_video.txt"


def _norm_url(url):
    """Normalize URL for comparison by extracting the unique ID part."""
    if not url: return ""
    url = url.strip().lower()
    
    # 1. Handle External iframes: https://fast.vimeo.net/embed/iframe/ID or https://example.wistia.net/embed/iframe/ID
    if "wistia.net/embed/iframe/" in url:
        return url.split("embed/iframe/")[-1].split("?")[0].strip("/")
        
    # 2. Handle Platform specific lesson URLs: .../posts/ID -> ID
    if "/posts/" in url:
        return url.split("/")[-1].split("?")[0].strip("/")
        
    # fallback to relative path without domain
    url = url.replace("https://www.example.com", "")
    url = url.replace("http://www.example.com", "")
    if url.endswith("/"): url = url[:-1]
    return url

def reconstruct():
    if not os.path.exists(CONTENT_FILE):
        print("❌ Error: Content file not found.")
        return

def _norm_title(title):
    """Normalize title for fuzzy matching by stripping all non-alphanumeric chars."""
    if not title: return ""
    # Remove icon text leftovers
    title = re.sub(r'(?i)video lesson icon.*?Sketch\.?', '', title)
    title = re.sub(r'(?i)default Created with Sketch\.?', '', title)
    # Remove numbering and leading symbols
    for _ in range(3):
        title = re.sub(r'^\d+[\s\|\.\-]*', '', title.strip())
        title = re.sub(r'^[\s\|\.\-]*', '', title.strip())
    # Strip everything except letters and numbers
    title = re.sub(r'[^a-zA-Z0-9]', '', title)
    return title.lower().strip()

def reconstruct():
    if not os.path.exists(CONTENT_FILE):
        print("❌ Error: Content file not found.")
        return

    # Load Backup for Metadata (Titles, Sections)
    backup_file = ".storage/downloaded_video_bak.txt"
    backup_map = {} # norm_url -> info
    title_map = {} # norm_title -> info
    
    if os.path.exists(backup_file):
        print(f"📖 Loading backup manifest: {backup_file}")
        current_course = "Unknown Course"
        current_section = "General"
        
        with open(backup_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Check Headers
                if line.startswith("# === "):
                    current_course = line.replace("# === ", "").split(" ===")[0].strip()
                    continue
                
                if line.startswith("## ---"):
                    current_section = line.replace("## ---", "").replace("---", "").strip()
                    continue
                
                # Parse Video Line
                clean_line = line
                while clean_line.startswith("#") or clean_line.startswith("[DONE]") or clean_line.startswith("[SKIPPED]") or clean_line.startswith(" "):
                    if clean_line.startswith("#"): clean_line = clean_line[1:].strip()
                    elif clean_line.startswith("[DONE]"): clean_line = clean_line[6:].strip()
                    elif clean_line.startswith("[SKIPPED]"): clean_line = clean_line[9:].strip()
                    else: clean_line = clean_line.strip()

                if "|" in clean_line:
                    parts = [p.strip() for p in clean_line.split("|")]
                    if len(parts) >= 3:
                        idx = parts[0].strip()
                        raw_title = parts[1].strip()
                        url_part = parts[2].split(" ")[0].strip()
                        
                        info = {
                            "title": raw_title,
                            "section": current_section,
                            "course": current_course,
                            "index": idx
                        }
                        
                        backup_map[_norm_url(url_part)] = info
                        title_map[_norm_title(raw_title)] = info
        print(f"   Mapped information for {len(backup_map)} records from backup.")

    print("📖 Loading content database...")
    with open(CONTENT_FILE, "r") as f:
        data = json.load(f)

    print(f"🔍 Found {len(data)} video records in database.")
    
    videos = []
    
    for video_url, info in data.items():
        json_title = info.get("title", "Unknown Title")
        n_json_title = _norm_title(json_title)

        # Infer default IDs
        course_name = "Restored Course"
        section_name = "Restored Section"
        cat_id = "000"
        post_id = 999
        
        course_url = info.get("course_url", "")
        if "products/" in course_url:
            parts = course_url.split("/")
            try:
                if "categories" in parts:
                    c_idx = parts.index("categories")
                    if len(parts) > c_idx + 1: cat_id = parts[c_idx + 1]
                if "posts" in parts:
                    po_idx = parts.index("posts")
                    if len(parts) > po_idx + 1: post_id = int(parts[po_idx + 1])
            except: pass

        # CHECK BACKUP
        norm_v = _norm_url(video_url)
        norm_c = _norm_url(course_url)
        
        # Priority 1: URL match (Wistia ID or Lesson URL)
        match = backup_map.get(norm_v) or backup_map.get(norm_c)
        
        # Priority 2: Exact Normalized Title match
        if not match:
            match = title_map.get(n_json_title)
            
        # Priority 3: Fuzzy "Title Contains" match
        if not match:
            for b_norm_title, b_info in title_map.items():
                if b_norm_title and (b_norm_title in n_json_title or n_json_title in b_norm_title):
                    match = b_info
                    break
            
        if match:
            # RESTORE EVERYTHING FROM BACKUP
            title = match['title']
            section_name = match['section']
            course_name = match['course']
            if match['index'].isdigit():
                post_id = int(match['index'])
        else:
            # Fallback to cleaned JSON title
            title = re.sub(r'^\d+[\s\|\.\-]*', '', json_title).strip()
            title = re.sub(r'(?i)video lesson icon.*?Sketch\.?', '', title).strip()
            section_name = f"Section {cat_id}" if cat_id != "000" else "Unknown Section"
            
        videos.append({
            "url": video_url,
            "title": title,
            "course": course_name,
            "category": section_name,
            "cat_sort": cat_id,
            "post_id": post_id 
        })








    # Sort
    # 1. Course Name
    # 2. Category Name (or ID) - To group them. 
    # But names are better. "Intro" comes before "Chapter 1"? Alphabetical isn't great.
    # We rely on the Original Index from Backup (post_id) which is 001, 002...
    # So if we sort by post_id (which came from backup index), we restore original order!
    
    print("🔄 Sorting videos (restoring original order)...")
    videos.sort(key=lambda x: (x["course"], x["post_id"]))

    print(f"💾 Writing manifest with {len(videos)} videos...")
    
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Index | Title | URL | Course | Section | Status\n")
        f.write(f"# RECONSTRUCTED FROM BACKUP + DB\n\n")
        
        curr_course = None
        curr_cat = None
        
        for idx, v in enumerate(videos, 1):
            if v["course"] != curr_course:
                f.write(f"\n# === {v['course']} ===\n")
                curr_course = v["course"]
                curr_cat = None
            
            if v["category"] != curr_cat:
                f.write(f"\n## --- {v['category']} ---\n")
                curr_cat = v["category"]

            line = f"{idx:03d} | {v['title']} | {v['url']} | {v['course']} | {v['category']}"
            f.write(f"{line}\n")

    print(f"✅ Success! Restored {len(videos)} videos to {MANIFEST_FILE}")

if __name__ == "__main__":
    reconstruct()
