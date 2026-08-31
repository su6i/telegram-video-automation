import os
import sys
import json
import asyncio
from dotenv import load_dotenv
from pyrogram import Client

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env
folder_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(folder_path, ".env"))

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = os.getenv("CHANNEL_ID")
# Use username if available for cleaner calls, else ID
CHANNEL_TARGET = os.getenv("CHANNEL_USERNAME") or CHANNEL_ID

# Storage directory
STORAGE_DIR = ".storage"
os.makedirs(STORAGE_DIR, exist_ok=True)
# Files
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
UPLOAD_HISTORY_FILE = os.path.join(STORAGE_DIR, "upload_history.json")
INDEX_STATE_FILE = os.path.join(STORAGE_DIR, "channel_index_info.json")

def parse_manifest():
    """Reads manifest and returns structured data: [ {course, section, index, title, url} ]"""
    videos = []
    if not os.path.exists(MANIFEST_FILE):
        return videos

    current_course = "Unknown"
    current_section = "General"
    
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            if line.startswith("# === "):
                content = line.replace("# === ", "").split(" ===")[0]
                if "(" in content:
                    current_course = content.split("(")[0].strip()
                else:
                    current_course = content
                current_section = "General"
            elif line.startswith("## --- "):
                current_section = line.replace("## --- ", "").replace(" ---", "").strip()
            elif " | " in line:
                # Video line, check for # [DONE]
                clean = line.replace("# [DONE] ", "")
                parts = clean.split(" | ")
                if len(parts) >= 3:
                    # Index | Title | URL OR Index | Section | Title | URL
                    # We assume Index | Title | URL based on scraper default
                    # But scraper has `if vid_section... write section` logic?
                    # Let's check parts.
                    vid_idx = parts[0]
                    vid_url = parts[-1]
                    
                    if len(parts) == 4:
                         # Index | Section | Title | URL
                         vid_title = parts[2]
                         vid_section_inline = parts[1] # Override current section?
                    else:
                         vid_title = parts[1]
                    
                    videos.append({
                        "course": current_course,
                        "section": current_section,
                        "index": vid_idx,
                        "title": vid_title,
                        "url": vid_url
                    })
    return videos

def load_history():
    if os.path.exists(UPLOAD_HISTORY_FILE):
        try:
            with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def load_state():
    if os.path.exists(INDEX_STATE_FILE):
        try:
            with open(INDEX_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"top_ids": [], "bottom_ids": []}

def save_state(state):
    with open(INDEX_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def generate_index_text(videos, history):
    """Generates a list of strings (blocks) < 4096 chars."""
    blocks = []
    current_block = ""
    
    last_course = None
    last_section = None
    
    header = "📚 **Course Index**\n\n"
    current_block += header
    
    for v in videos:
        # Group Headers
        if v['course'] != last_course:
            course_head = f"\n🎓 **{v['course']}**\n"
            if len(current_block) + len(course_head) > 4000:
                blocks.append(current_block)
                current_block = header + course_head # Repeat header on new page? Or just course head
            else:
                current_block += course_head
            last_course = v['course']
            last_section = None # Reset section
            
        if v['section'] != last_section and v['section'] != "General":
            sect_head = f"\n📂 __{v['section']}__\n"
            if len(current_block) + len(sect_head) > 4000:
                blocks.append(current_block)
                current_block = sect_head
            else:
                current_block += sect_head
            last_section = v['section']
            
        # Line
        # Check history for link
        idx = v['index']
        hist = history.get(idx)
        
        line = ""
        if hist and hist.get('link'):
            line = f"{idx} - [{v['title']}]({hist['link']})\n"
        else:
             # No link yet
            line = f"{idx} - {v['title']}\n"
            
        if len(current_block) + len(line) > 4000:
            blocks.append(current_block)
            current_block = line
        else:
            current_block += line
            
    if current_block:
        blocks.append(current_block)
        
    return blocks

async def main():
    print("🔄 Generating Index...")
    videos = parse_manifest()
    history = load_history()
    print(f"   Found {len(videos)} videos in manifest.")
    print(f"   Found {len(history)} items in upload history.")
    
    blocks = generate_index_text(videos, history)
    print(f"   Generated {len(blocks)} message blocks.")
    
    state = load_state()
    
    if not API_ID or not API_HASH:
         print("❌ Missing API_ID/API_HASH. Cannot edit channel messages.")
         return

    async with Client("index_bot", api_id=API_ID, api_hash=API_HASH) as app:
        # Resolve target
        try:
            target = CHANNEL_TARGET
            if str(target).isdigit() or str(target).startswith("-"):
                 target = int(target)
            chat = await app.get_chat(target)
            print(f"✅ Connected to channel: {chat.title}")
        except Exception as e:
            print(f"❌ Could not connect to channel: {e}")
            return

        # 1. Update TOP messages
        new_top_ids = []
        for i, text in enumerate(blocks):
            msg_id = None
            if i < len(state['top_ids']):
                msg_id = state['top_ids'][i]
                try:
                    await app.edit_message_text(chat.id, msg_id, text)
                    print(f"   ✏️ Updated Top Msg {msg_id}")
                except Exception as e:
                    print(f"   ⚠️ Failed to edit Top Msg {msg_id}: {e}")
                    # If edit failed (deleted?), send new?
                    # Assuming strict preservation of IDs is preferred, but if gone, we must send new.
                    msg = await app.send_message(chat.id, text)
                    msg_id = msg.id
                    print(f"   ➕ Sent Replacment Top Msg {msg_id}")
            else:
                # New message needed
                msg = await app.send_message(chat.id, text)
                msg_id = msg.id
                print(f"   ➕ Sent New Top Msg {msg_id}")
            
            new_top_ids.append(msg_id)
            await asyncio.sleep(2) # Flood protection
            
        state['top_ids'] = new_top_ids
        
        # 2. Update BOTTOM messages
        # Strategy: Delete old bottom messages, Send new ones.
        for old_id in state['bottom_ids']:
            try:
                await app.delete_messages(chat.id, old_id)
                print(f"   🗑 Deleted Old Bottom Msg {old_id}")
            except:
                pass
        
        new_bottom_ids = []
        for text in blocks:
             msg = await app.send_message(chat.id, text)
             new_bottom_ids.append(msg.id)
             print(f"   ➕ Sent New Bottom Msg {msg.id}")
             await asyncio.sleep(2)
             
        state['bottom_ids'] = new_bottom_ids
        
        save_state(state)
        print("✅ Index Updated Successfully.")

if __name__ == "__main__":
    asyncio.run(main())
