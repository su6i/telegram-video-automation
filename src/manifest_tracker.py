"""
Manifest manager — track video processing and upload status in downloaded_video.txt
"""
import os
import re
from pathlib import Path


STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
UPLOAD_HISTORY_FILE = os.path.join(STORAGE_DIR, "upload_history.json")


def _index_line_re(index):
    """Match a manifest line for this index in either the compact
    "NNN_Title | URL" format the manifest is generated in, or the
    "NNN | TITLE | URL[ | STATUS]" format update_manifest_status expands
    it into once a status is written."""
    return re.compile(rf'^{re.escape(index)}(?:_|\s*\|)')


def parse_manifest_line(line):
    """Parse one manifest line into (index, title, url, status).

    Understands both formats the manifest carries:
      "NNN_Title | URL"                     as generated
      "NNN | TITLE | URL[ | STATUS]"        after update_manifest_status
    A "# [DONE] " prefix counts as an uploaded line. Section headers
    ("# === Course ===", "## --- Section ---"), blank lines and plain
    comments return None.
    """
    raw = (line or "").strip()
    if not raw or "|" not in raw:
        return None

    done_prefix = raw.startswith("# [DONE]")
    if done_prefix:
        raw = raw[len("# [DONE]"):].strip()
    elif raw.startswith("#"):
        return None

    parts = [p.strip() for p in raw.split("|")]
    compact = re.match(r'^(\d{3})_(.*)$', parts[0])
    if compact:
        index, title = compact.group(1), compact.group(2).strip()
        url = parts[1] if len(parts) >= 2 else ""
        status = parts[2] if len(parts) >= 3 else ""
    elif re.fullmatch(r'\d{3}', parts[0]):
        index = parts[0]
        title = parts[1] if len(parts) >= 2 else ""
        url = parts[2] if len(parts) >= 3 else ""
        status = parts[3] if len(parts) >= 4 else ""
    else:
        return None

    if done_prefix and not status:
        status = "✅ UPLOADED"
    return index, title, url, status


def _iter_manifest_lines():
    if not os.path.exists(MANIFEST_FILE):
        return
    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            parsed = parse_manifest_line(line)
            if parsed:
                yield parsed


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
        line_re = _index_line_re(index)
        for i, line in enumerate(lines):
            if line_re.match(line):
                # Parse line — handle both the compact "NNN_Title | URL"
                # format the manifest is generated in, and an already
                # expanded "NNN | TITLE | URL[ | STATUS]" format.
                parts = line.split('|')
                if len(parts) >= 2:
                    first = parts[0].strip()
                    compact = re.match(r'^(\d{3})_(.*)$', first)
                    if compact:
                        idx, title = compact.group(1), compact.group(2)
                        url = parts[1].strip()
                    else:
                        idx = first
                        title = parts[1].strip()
                        url = parts[2].strip() if len(parts) >= 3 else ""

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
    """Get status of a video from manifest ("" when it has none)."""
    for idx, _title, _url, status in _iter_manifest_lines():
        if idx == index:
            return status or None
    return None


def get_pending_videos():
    """Get all videos without an upload status."""
    return [
        {'index': idx, 'title': title, 'url': url}
        for idx, title, url, status in _iter_manifest_lines()
        if not status
    ]


def get_uploaded_videos():
    """Get all uploaded videos."""
    return [
        {'index': idx, 'title': title, 'url': url, 'status': status}
        for idx, title, url, status in _iter_manifest_lines()
        if 'UPLOADED' in status
    ]


def get_failed_videos():
    """Get all failed videos."""
    return [
        {'index': idx, 'title': title, 'url': url, 'status': status}
        for idx, title, url, status in _iter_manifest_lines()
        if 'FAILED' in status
    ]


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
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.startswith("# === "):
                    current_course = stripped.replace("# === ", "").split(" ===")[0].split("(")[0].strip()
                    current_section = "General"
                    continue
                if stripped.startswith("## --- "):
                    current_section = stripped.replace("## --- ", "").replace(" ---", "").strip()
                    continue

                parsed = parse_manifest_line(stripped)
                if not parsed:
                    continue
                index, title, url, status = parsed
                videos.append({
                    'index': index,
                    'title': title,
                    'url': url,
                    'course': current_course,
                    'section': current_section,
                    'is_done': 'UPLOADED' in status,
                })
    except Exception as e:
        print(f"⚠️ Error reading manifest sequence: {e}")

    return videos
