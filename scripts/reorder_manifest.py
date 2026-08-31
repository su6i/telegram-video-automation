import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.manifest_manager import ManifestManager

def reorder():
    storage_dir = ".storage"
    manifest_path = os.path.join(storage_dir, "downloaded_video.txt")
    
    if not os.path.exists(manifest_path):
        print(f"❌ No manifest found at {manifest_path}")
        return

    print(f"📂 Reading existing manifest: {manifest_path}")
    
    # Manually parsing to avoid strict 'fresh_video' dependency of save_manifest
    videos = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                # Format: Index | Title | URL | Course | Section
                v = {
                    'index': parts[0],
                    'title': parts[1],
                    'url': parts[2],
                    'course_title': parts[3] if len(parts) > 3 else "Unknown Course",
                    'section': parts[4] if len(parts) > 4 else "General",
                    'subsection': None, # Best effort
                    'is_done': False # We preserve status logic via save_manifest if needed, but here just valid entries
                }
                # Try to preserve done status from comments? 
                # Actually ManifestManager.save_manifest is smart enough to preserve OLD status data
                # if we pass it as "fresh" data.
                videos.append(v)

    if not videos:
        print("❌ No videos found in manifest to reorder.")
        return

    print(f"📊 Found {len(videos)} videos. Re-sorting...")
    
    # Use the Manager to Save (it handles sorting internally now!)
    mgr = ManifestManager(storage_dir=storage_dir)
    mgr.save_manifest(videos)
    
    print("✅ Manifest reordered and saved!")

if __name__ == "__main__":
    reorder()
