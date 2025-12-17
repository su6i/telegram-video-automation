from pyrogram import Client
from dotenv import load_dotenv
import os
import sys
import re

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
# Use the same logic as process_and_upload to find the ID
channel_username = os.getenv("CHANNEL_USERNAME") or os.getenv("CHANNEL_ID")

if not api_id or not api_hash:
    print("❌ API Credentials missing in .env")
    exit(1)

# Ensure ID is int if possible
if channel_username and (str(channel_username).startswith('-') or str(channel_username).isdigit()):
    try:
        channel_username = int(channel_username)
    except ValueError:
        pass

app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)

async def main():
    async with app:
        print(f"🔍 Connecting to channel: {channel_username} ...")
        
        # Verify access first (using the logic we added to process_and_upload)
        target_chat = None
        try:
            target_chat = await app.get_chat(channel_username)
            print(f"✅ Connected to: {target_chat.title}")
        except Exception as e:
            print(f"⚠️ Direct access failed ({e}). Checking dialogs...")
            async for dialog in app.get_dialogs():
                if dialog.chat.id == channel_username:
                    target_chat = dialog.chat
                    print(f"✅ Found in dialogs: {target_chat.title}")
                    break
        
        if not target_chat:
            print("❌ Channel not found! Run scripts/diagnose_channel.py first.")
            return

        print("\n📥 Fetching message history (Videos only)...")
        print(f"{'ID':<10} | {'Date':<20} | {'Caption (Title)':<50}")
        print("-" * 85)
        
        video_count = 0
        latest_id = 0
        
        # Iterate over history
        # Note: Pyrogram yields newest first by default
        messages = []
        async for msg in app.get_chat_history(target_chat.id):
            if msg.video:
                caption = msg.caption or "No Caption"
                # Remove newlines for cleaner table
                clean_caption = caption.split('\n')[0][:45]
                messages.append({
                    "id": msg.id,
                    "date": msg.date,
                    "caption": clean_caption,
                    "full_caption": caption
                })
                video_count += 1
                if msg.id > latest_id:
                    latest_id = msg.id

        # Sort by ID (oldest first) to see the sequence
        messages.sort(key=lambda x: x['id'])
        
        found_numbers = set()
        for m in messages:
            print(f"{m['id']:<10} | {str(m['date']):<20} | {m['caption']}")
            # Extract number prefix
            match =  re.search(r'^(\d+)', m['full_caption'])
            if match:
                found_numbers.add(int(match.group(1)))
            
        print("-" * 85)
        print(f"📊 Total Videos Found: {video_count}")
        print(f"🔑 Latest Message ID: {latest_id}")
        
        # Analyze Gaps
        if found_numbers:
            max_num = max(found_numbers)
            all_nums = set(range(1, max_num + 1))
            missing = sorted(list(all_nums - found_numbers))
            
            print("\n🚨 Missing Video Numbers:")
            if missing:
                print(f"   {', '.join(map(str, missing))}")
                print(f"   Count: {len(missing)}")
            else:
                print(f"   ✅ No gaps found! Sequence 1-{max_num} is complete.")
        else:
            print("\n⚠️ No numbered videos found (e.g. '001 - Title').")

if __name__ == "__main__":
    app.run(main())
