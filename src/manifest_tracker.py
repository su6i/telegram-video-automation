"""
Manifest manager — track video processing and upload status in downloaded_video.txt
"""
import os
import re
from pathlib import Path


STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
UPLOAD_HISTORY_FILE = os.path.join(STORAGE_DIR, "upload_history.json")


def update_manifest_status(index, status, msg_id=None, link=None):
    """
    Update status of a video in manifest.
    Status: UPLOADED, PROCESSING, FAILED, or empty (pending)
    
    Args:
        index: "001", "002", etc.
        status: "UPLOADED" | "PROCESSING" | "FAILED" | None
        msg_id: Telegram message ID (optional)
        link: Telegram link (optional)
    """
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ Manifest not found: {MANIFEST_FILE}")
        return False
    
    try:
        lines = []
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        updated = False
        for i, line in enumerate(lines):
            # Look for line starting with this index
            if re.match(rf'^{index}\s*\|', line):
                # Parse line
                parts = line.split('|')
                if len(parts) >= 3:
                    # Format: INDEX | TITLE | URL | [STATUS]
                    idx = parts[0].strip()
                    title = parts[1].strip()
                    url = parts[2].strip()
                    
                    # Build status string
                    if status == "UPLOADED":
                        status_str = f"✅ UPLOADED (msg_id: {msg_id})"
                    elif status == "PROCESSING":
                        status_str = "⏳ PROCESSING"
                    elif status == "FAILED":
                        status_str = "❌ FAILED"
                    else:
                        status_str = ""
                    
                    # Rebuild line
                    if status_str:
                        new_line = f"{idx} | {title} | {url} | {status_str}\n"
                    else:
                        new_line = f"{idx} | {title} | {url}\n"
                    
                    lines[i] = new_line
                    updated = True
                    break
        
        if updated:
            with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return True
        
        return False
    
    except Exception as e:
        print(f"❌ Error updating manifest: {e}")
        return False


def get_video_status(index):
    """Get status of a video from manifest."""
    if not os.path.exists(MANIFEST_FILE):
        return None
    
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if re.match(rf'^{index}\s*\|', line):
                    parts = line.split('|')
                    if len(parts) >= 4:
                        return parts[3].strip()
                    return None
        return None
    except:
        return None


def get_pending_videos():
    """Get all videos without upload status."""
    if not os.path.exists(MANIFEST_FILE):
        return []
    
    pending = []
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                # Skip comments and headers
                if line.startswith('#'):
                    continue
                
                # Check if it has a status
                parts = line.split('|')
                if len(parts) >= 3:
                    idx = parts[0].strip()
                    # If it's a valid index (3 digits) and no status column
                    if idx.isdigit() and len(parts) == 3:
                        title = parts[1].strip()
                        url = parts[2].strip()
                        pending.append({'index': idx, 'title': title, 'url': url})
    except:
        pass
    
    return pending


def get_uploaded_videos():
    """Get all uploaded videos."""
    if not os.path.exists(MANIFEST_FILE):
        return []
    
    uploaded = []
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if '✅ UPLOADED' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        idx = parts[0].strip()
                        title = parts[1].strip()
                        status = parts[3].strip()
                        uploaded.append({'index': idx, 'title': title, 'status': status})
    except:
        pass
    
    return uploaded


def get_failed_videos():
    """Get all failed videos."""
    if not os.path.exists(MANIFEST_FILE):
        return []
    
    failed = []
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if '❌ FAILED' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        idx = parts[0].strip()
                        title = parts[1].strip()
                        status = parts[3].strip()
                        failed.append({'index': idx, 'title': title, 'status': status})
    except:
        pass
    
    return failed


def get_all_manifest_videos():
    """Get all videos defined in manifest in their listed order."""
    if not os.path.exists(MANIFEST_FILE):
        return []
    
    videos = []
    try:
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
                    clean_line = line.replace("# [DONE] ", "").strip()
                    parts = [p.strip() for p in clean_line.split("|")]
                    if len(parts) >= 2:
                        # Extract index from parts[0] which might be "001" or "001_Title"
                        idx_match = re.match(r'^(\d{3})', parts[0])
                        if idx_match:
                            index = idx_match.group(1)
                            # Title logic
                            if "_" in parts[0] and len(parts[0]) > 4:
                                title = parts[0][4:].strip()
                            else:
                                title = parts[1] if len(parts) >= 2 else ""
                            
                            url = parts[1] if "_" in parts[0] else (parts[2] if len(parts) >= 3 else "")
                            
                            videos.append({
                                'index': index,
                                'title': title,
                                'url': url,
                                'course': current_course,
                                'section': current_section,
                                'is_done': "# [DONE]" in line or "UPLOADED" in line
                            })
    except Exception as e:
        print(f"⚠️ Error reading manifest sequence: {e}")
        
    return videos
