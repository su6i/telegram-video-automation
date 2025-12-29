
import json
import os

CONTENT_FILE = ".storage/scraped_content.json"

def deduplicate():
    if not os.path.exists(CONTENT_FILE):
        return

    with open(CONTENT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    cleaned = {}
    course_to_key = {}
    
    # Sort keys to ensure consistent behavior (optional but helps)
    keys = sorted(data.keys())
    
    for k in keys:
        v = data[k]
        url = v.get("course_url")
        
        if not url:
            cleaned[k] = v
            continue
            
        if url not in course_to_key:
            course_to_key[url] = k
            cleaned[k] = v
        else:
            prev_key = course_to_key[url]
            # Preference Logic:
            # 1. Wistia Keys (contain 'wistia') are usually better
            # 2. Longer descriptions are usually better
            
            p_is_wistia = "wistia" in prev_key
            k_is_wistia = "wistia" in k
            
            p_desc_len = len(cleaned[prev_key].get("description", ""))
            k_desc_len = len(v.get("description", ""))
            
            replace = False
            if k_is_wistia and not p_is_wistia:
                replace = True
            elif k_is_wistia == p_is_wistia:
                if k_desc_len > p_desc_len:
                    replace = True
            
            if replace:
                del cleaned[prev_key]
                course_to_key[url] = k
                cleaned[k] = v
                
    print(f"Original: {len(data)}, Cleaned: {len(cleaned)}")
    
    with open(CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    deduplicate()
