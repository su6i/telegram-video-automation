import os
import re
import shutil

FILES_TXT = ".storage/files.txt"
MANIFEST_FILE = ".storage/downloaded_video.txt"

def normalize_title(text):
    # Remove extension
    text = os.path.splitext(text)[0]
    # Remove leading index like 050_ or 001 |
    text = re.sub(r'^\d+[\s\-\_\.\|]+', '', text)
    # Remove inner numbering like "1 - ", "1 | "
    text = re.sub(r'^\d+[\s\-\_\.\|]+', '', text)
    # Lowercase and alpha
    return re.sub(r'[^a-z0-9]', '', text.lower())

def main():
    if not os.path.exists(FILES_TXT):
        print(f"File {FILES_TXT} not found.")
        return

    # 1. Build Map from files.txt
    print("Reading files.txt...")
    file_map = {} # norm_title -> index_str
    
    with open(FILES_TXT, 'r') as f:
        for line in f:
            line = line.strip()
            # Extract filename from tree output: "│   ├── 050_..."
            # Find the part that looks like a filename
            match = re.search(r'(\d{3})_(.+)\.mp4', line)
            if match:
                idx = match.group(1)
                raw_title = match.group(2)
                norm = normalize_title(raw_title)
                file_map[norm] = idx
                # print(f"Mapped: {norm} -> {idx}")
    
    print(f"Found {len(file_map)} files to align.")
    
    # 2. Update Manifest
    new_lines = []
    updated_count = 0
    
    with open(MANIFEST_FILE, 'r') as f:
        for line in f:
            if line.strip().startswith("#") or "|" not in line:
                new_lines.append(line)
                continue
                
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                current_idx = parts[0]
                title = parts[1]
                
                norm = normalize_title(title)
                
                if norm in file_map:
                    new_idx = file_map[norm]
                    if new_idx != current_idx:
                        # Update index
                        parts[0] = new_idx
                        new_lines.append(" | ".join(parts) + "\n")
                        updated_count += 1
                        # print(f"Updated {title}: {current_idx} -> {new_idx}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
    # 3. Save
    shutil.copy(MANIFEST_FILE, MANIFEST_FILE + ".bak")
    with open(MANIFEST_FILE, 'w') as f:
        f.writelines(new_lines)
        
    print(f"✅ Updated {updated_count} lines in manifest.")

if __name__ == "__main__":
    main()
