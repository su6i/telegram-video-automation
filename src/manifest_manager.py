import os
import shutil
import threading
from datetime import datetime

class ManifestManager:
    def __init__(self, storage_dir=".storage", manifest_filename="downloaded_video.txt"):
        self.storage_dir = storage_dir
        self.manifest_file = os.path.join(storage_dir, manifest_filename)
        self.lock = threading.Lock()
        os.makedirs(self.storage_dir, exist_ok=True)

    def backup(self):
        """Creates a timestamped backup of the manifest file."""
        if os.path.exists(self.manifest_file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"downloaded_video_backup_{timestamp}.txt"
            backup_path = os.path.join(self.storage_dir, backup_name)
            shutil.copy2(self.manifest_file, backup_path)
            
            # Also maintain a 'latest' backup
            latest_backup = os.path.join(self.storage_dir, "downloaded_video.txt.bak")
            shutil.copy2(self.manifest_file, latest_backup)
            return backup_path
        return None

    def mark_video_completed(self, index_str):
        """Marks a video as completed in the manifest file by commenting it out (adding [DONE])."""
        with self.lock:
            try:
                self.backup()
                lines = []
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                with open(self.manifest_file, "w", encoding="utf-8") as f:
                    for line in lines:
                        if line.strip().startswith(f"{index_str} |"):
                            # Check if already done
                            if "# [DONE]" not in line:
                                f.write(f"# [DONE] {line}")
                                print(f"   📝 Marked {index_str} as done in manifest.")
                            else:
                                f.write(line)
                        else:
                            f.write(line)
            except Exception as e:
                print(f"   ❌ Error marking video as done: {e}")

    def save_manifest(self, videos, limit=None):
        """
        Saves the list of discovered videos to the manifest.
        Handles merging with existing data to update metadata while preserving history.
        """
        # Backup before any write operation
        self.backup()
        
        # 1. Deduplicate & Prepare Fresh Map
        fresh_videos_map = {}
        for v in videos:
            if not v.get('url'): continue # Skip if no URL
            n_url = v['url'].strip().rstrip("/")
            if n_url not in fresh_videos_map:
                fresh_videos_map[n_url] = v
        
        # 2. Load EXISTING manifest
        final_videos = []
        processed_urls = set()
        
        def _norm_url(u):
            return u.strip().rstrip("/")
        
        max_index = 0
        if os.path.exists(self.manifest_file):
            try:
                with open(self.manifest_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("# Index"): continue
                        
                        # Preserve "Done" status
                        is_done = "# [DONE]" in line
                        clean_line = line.replace("# [DONE]", "").strip()
                        if clean_line.startswith("#"): continue
                            
                        if "|" in clean_line:
                            parts = [p.strip() for p in clean_line.split("|")]
                            if len(parts) >= 3:
                                idx_str = parts[0]
                                title = parts[1]
                                url = parts[2]
                                course = parts[3] if len(parts) > 3 else 'Unknown'
                                section = parts[4] if len(parts) > 4 else 'General'
                                
                                if not url.startswith("http"): continue
                                
                                if idx_str.isdigit():
                                    max_index = max(max_index, int(idx_str))
                                
                                norm_url = _norm_url(url)
                                processed_urls.add(norm_url)
                                
                                # Default to existing
                                vid_data = {
                                    'index': idx_str,
                                    'url': url,
                                    'is_done': is_done,
                                    'title': title,
                                    'course_title': course,
                                    'section': section,
                                    'category': section,
                                    'subsection': None
                                }
                                
                                # UPGRADE with Fresh Metadata if available
                                if norm_url in fresh_videos_map:
                                    fresh = fresh_videos_map[norm_url]
                                    vid_data['title'] = fresh.get('title', title)
                                    vid_data['course_title'] = fresh.get('course_title', course)
                                    vid_data['section'] = fresh.get('section', section)
                                    vid_data['category'] = fresh.get('category', section)
                                    vid_data['subsection'] = fresh.get('subsection', None)
                                
                                final_videos.append(vid_data)
            except Exception as e:
                print(f"⚠️ Could not read existing manifest: {e}")
                
        # 3. Add NEW videos
        new_found = []
        for v in videos:
            if not v.get('url'): continue
            n_url = v['url'].strip().rstrip("/")
            if n_url not in processed_urls:
                v_data = {
                    'index': None, # To be assigned
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
        
        final_videos.extend(new_found)
        
        # 4. Renumber Sequentially
        for idx, v in enumerate(final_videos, 1):
            v['index'] = f"{idx:03d}"
        
        # 5. Write Manifest
        with self.lock:
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                f.write(f"# Index | Title | URL | Course | Section | Status\n")
                f.write(f"# To skip a video, delete the line or put a '#' at the start\n")
                
                current_course = None
                current_category = None
                current_subsection_header = None
                
                for v in final_videos:
                    c_title = v['course_title']
                    cat = v.get('category', v['section'])
                    sub = v.get('subsection')
                    sec_name = v['section']
                    
                    if c_title != current_course:
                        current_course = c_title
                        count = sum(1 for x in final_videos if x['course_title'] == c_title)
                        f.write(f"\n# === {c_title} ({count} videos) ===\n")
                        current_category = None
                        current_subsection_header = None
                    
                    actual_cat = cat if cat else sec_name
                    if actual_cat != current_category:
                        f.write(f"\n## --- {actual_cat} ---\n")
                        current_category = actual_cat
                        current_subsection_header = None
                    
                    if sub and sub != actual_cat:
                        if sub != current_subsection_header:
                            f.write(f"### {sub}\n")
                            current_subsection_header = sub
                    
                    status_pfx = "# [DONE] " if v.get('is_done') else ""
                    clean_title = v['title'].replace("\n", " ").strip()
                    
                    # Ensure at least 3 columns for parsing
                    line = f"{v['index']} | {clean_title} | {v['url']} | {c_title} | {sec_name}"
                    f.write(f"{status_pfx}{line}\n")
                
                print(f"   ✅ Manifest saved: {len(final_videos)} entries")
