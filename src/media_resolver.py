"""
Media path resolver — handle multiple video directories across different drives.
"""
import os
import json
from pathlib import Path


STORAGE_DIR = ".storage"
MEDIA_PATHS_FILE = os.path.join(STORAGE_DIR, "media_paths.json")


def load_media_paths():
    """Load configured media paths from .storage/media_paths.json"""
    if not os.path.exists(MEDIA_PATHS_FILE):
        # Default fallback
        return ["downloads"]
    
    try:
        with open(MEDIA_PATHS_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            paths = config.get("paths", [])
            if not paths:
                return ["downloads"]
            
            # Convert relative paths to absolute
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            result = []
            for path in paths:
                if os.path.isabs(path):
                    result.append(path)
                else:
                    result.append(os.path.join(repo_root, path))
            return result
    except Exception as e:
        print(f"⚠️ Error loading media_paths.json: {e}")
        return ["downloads"]


def find_video_file(filename):
    """
    Search for a video file across all configured media paths (recursively).
    Returns full path if found, else None.
    """
    paths = load_media_paths()
    
    for base_path in paths:
        # Walk recursively
        for root, dirs, files in os.walk(base_path):
            if filename in files:
                full_path = os.path.join(root, filename)
                if os.path.exists(full_path):
                    return full_path
    
    return None


def list_all_videos():
    """
    Scan all configured media paths (recursively) and return list of video files.
    Returns: [(filename, full_path), ...]
    """
    paths = load_media_paths()
    videos = []
    
    for base_path in paths:
        if not os.path.exists(base_path):
            print(f"⚠️ Media path not found: {base_path}")
            continue
        
        # Walk recursively through all subdirectories
        for root, dirs, files in os.walk(base_path):
            # Exclude processed directories to avoid duplicates/loops
            dirs[:] = [d for d in dirs if d not in ["telegram_processed", "processed"]]
            
            for f in files:
                if f.startswith("._"):
                    continue
                if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    full_path = os.path.join(root, f)
                    if os.path.isfile(full_path):
                        videos.append((f, full_path))
    
    return videos
