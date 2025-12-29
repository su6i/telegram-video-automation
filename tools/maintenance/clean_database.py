
import json
import os
import re

CONTENT_FILE = ".storage/scraped_content.json"
BACKUP_FILE = ".storage/scraped_content.json.pre_clean"

def clean():
    if not os.path.exists(CONTENT_FILE):
        print("❌ Error: Content file not found.")
        return

    # Backup
    if not os.path.exists(BACKUP_FILE):
        import shutil
        shutil.copy2(CONTENT_FILE, BACKUP_FILE)
        print(f"📦 Backup created at {BACKUP_FILE}")

    print("📖 Loading content database...")
    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned_count = 0
    title_fixes = 0
    desc_fixes = 0

    for url, info in data.items():
        original_title = info.get("title", "")
        original_desc = info.get("description", "")

        # --- Clean Title ---
        # 1. Remove icon/sketch junk
        title = re.sub(r'video lesson icon.*?Sketch\.?', '', original_title, flags=re.IGNORECASE).strip()
        # 2. Remove leaked instructions/body text
        title = re.sub(r'Instructions:.*', '', title, flags=re.IGNORECASE).strip()
        
        # 3. Handle "Bleeding" titles (where the header contains intro text)
        stop_keywords = [
            "What's covered", "What is covered", "In this lesson", 
            "✅", "💰", "🚀", "Instructions", "Wait!",
            "Follow Along Step by Step", "Access the footage here",
            "Exclusive Student Discount", "Claim Your Discount",
            "Viral Video Inspiration", "Coupon Code", "CLICK HERE",
            "As a student", "Get your student discount", "Watch Here",
            "Check out these", "Check out this", "Free Preview"
        ]
        for kw in stop_keywords:
            if kw.lower() in title.lower():
                # Find lowercase match but split original
                start_idx = title.lower().find(kw.lower())
                title = title[:start_idx].strip()



        # 4. Remove leading numbering
        title = re.sub(r'^\d+[\s\|\-]*', '', title).strip()
        
        # 5. Final aggressive truncation for long leaked titles
        if len(title) > 80:
             # If it has a period or newline, it's likely leaked text
             if '\n' in title:
                 title = title.split('\n')[0].strip()
             elif '. ' in title:
                 title = title.split('. ')[0].strip()


        # --- Clean Description ---
        desc = original_desc
        # 1. Strip Comment Section (Major Junk)
        # Matches "Comments\n123\nPost Comment" and everything after
        comment_pattern = r'(?m)^Comments\s*\n\d+\s*\nPost Comment.*'
        if re.search(comment_pattern, desc):
            desc = re.split(comment_pattern, desc)[0].strip()

        # 2. Strip standard comment footers if they leaked
        desc = re.sub(r'(?m)^REPLY\s*\n.*', '', desc)
        desc = re.sub(r'(?m)^\d+ (minutes|hours|days|weeks|months) ago.*', '', desc)
        
        # 3. Final trim
        desc = desc.strip()

        # Update if changed
        if title != original_title:
            info["title"] = title
            title_fixes += 1
        if desc != original_desc:
            info["description"] = desc
            desc_fixes += 1
        
        if title != original_title or desc != original_desc:
            cleaned_count += 1

    print(f"✨ Cleaning Summary:")
    print(f"   - Total Entries: {len(data)}")
    print(f"   - Titles Fixed: {title_fixes}")
    print(f"   - Descriptions Fixed: {desc_fixes}")
    print(f"   - Total Modified: {cleaned_count}")

    with open(CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Successfully wrote cleaned database to {CONTENT_FILE}")

if __name__ == "__main__":
    clean()
