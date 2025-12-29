import os

# Storage directory
STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
# Fallback to root for backward compatibility
if not os.path.exists(MANIFEST_FILE):
    MANIFEST_FILE = "downloaded_video.txt"

def verify_manifest():
    if not os.path.exists(MANIFEST_FILE):
        print(f"❌ {MANIFEST_FILE} not found.")
        return

    urls = []
    duplicates = []
    total_lines = 0
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            total_lines += 1
            parts = line.split("|")
            if len(parts) >= 3:
                url = parts[-1].strip()
                if url in urls:
                    duplicates.append(url)
                urls.add(url) if isinstance(urls, set) else urls.append(url)

    print(f"📊 Manifest Verification:")
    print(f"   - Total Videos: {total_lines}")
    print(f"   - Unique URLs: {len(set(urls))}")
    
    if duplicates:
        print(f"   ❌ Found {len(duplicates)} duplicates!")
        for d in duplicates[:5]:
            print(f"      - {d}")
    else:
        print(f"   ✅ No duplicates found.")

if __name__ == "__main__":
    verify_manifest()
