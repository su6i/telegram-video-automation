import argparse
import asyncio
import json
import os
import pathlib
import sys

from dotenv import load_dotenv
from pyrogram import Client

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts scripts/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path
from src.index_builder import build_index_or_fail, read_manifest

# Load env
load_dotenv(env_path())

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = os.getenv("CHANNEL_ID")
# Use username if available for cleaner calls, else ID
CHANNEL_TARGET = os.getenv("CHANNEL_USERNAME") or CHANNEL_ID

# Storage directory
STORAGE_DIR = ".storage"
# Files
INDEX_STATE_FILE = os.path.join(STORAGE_DIR, "channel_index_info.json")
# ids 685-691, fixed forever. 692+ are resource *documents*: a document cannot be
# edited into a text message, a message cannot be moved, and deleting one only makes
# its id permanently un-editable. There is no eighth slot and there never will be.
BOTTOM_INDEX_SLOTS = 7


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

async def main():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    print("🔄 Generating Index...")
    
    entries = read_manifest()
    
    data = pathlib.Path(os.getenv(
        "TVA_DATA",
        "/Users/su6i/.local/share/agent-projects/telegram-video-automation/data"))
    
    mp = json.loads((data / "message_ids.json").read_text(encoding="utf-8"))
    attach_state = json.loads(
        (data / "attachments_state.json").read_text(encoding="utf-8"))
    msg_of = {k: (v if isinstance(v, int) else v.get("video")) for k, v in mp.items()}
    
    chat_id = int(CHANNEL_ID)
    internal = abs(chat_id) - 1000000000000
    
    blocks = build_index_or_fail(
        entries, msg_of, internal, attach_state, BOTTOM_INDEX_SLOTS,
        "scripts/generate_index.py", include_resource=False, include_subtitle=True
    )
    
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
    parser = argparse.ArgumentParser(description="Generate and update course index in Telegram channel.")
    parser.parse_args()
    asyncio.run(main())
