import os
import json
import re

STORAGE_DIR = ".storage"
MEDIA_PATHS_FILE = os.path.join(STORAGE_DIR, "media_paths.json")

def normalize_title(filename):
    """
    Normalize filename for fuzzy matching.
    Removes leading index numbers (001_), extension, and special chars.
    """
    # Remove extension
    name = os.path.splitext(filename)[0]
    
    # Remove leading numbers/hyphens/underscores pattern (e.g. "001_", "01 - ", "1.")
    name = re.sub(r'^\d+[\s\-\_\.]+', '', name)
    
    # Lowercase and remove non-alphanumeric
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
                        norm = normalize_title(file)
                        if norm:
                            self.index[norm] = os.path.join(root, file)
                            count += 1
        print(f"✅ Indexed {count} existing videos from media library.")

    def find_file(self, title):
        """Check if video title exists in index."""
        norm = normalize_title(title)
        return self.index.get(norm)
