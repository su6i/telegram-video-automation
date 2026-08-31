
import json
import os

CONTENT_FILE = ".storage/scraped_content.json"
BACKUP_FILE = ".storage/scraped_content.json.pre_clean"

def restore_descriptions():
    if not os.path.exists(CONTENT_FILE) or not os.path.exists(BACKUP_FILE):
        print("❌ Error: Files not found.")
        return

    print("📖 Loading clean database...")
    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        clean_data = json.load(f)

    print("📖 Loading backup database...")
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    restored_count = 0

    for url, info in clean_data.items():
        if url in backup_data:
            original_desc = backup_data[url].get("description", "")
            current_desc = info.get("description", "")
            
            if original_desc != current_desc:
                info["description"] = original_desc
                restored_count += 1

    print(f"🔄 Restored descriptions for {restored_count} entries.")

    with open(CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Descriptions restored to {CONTENT_FILE}")

if __name__ == "__main__":
    restore_descriptions()
