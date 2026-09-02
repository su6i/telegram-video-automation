import os
import pathlib
import sys

from dotenv import load_dotenv
from pyrogram import Client

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts tools/debug/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path

# Load from root .env
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(env_path())

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
target_id = os.getenv("CHANNEL_ID") or os.getenv("CHANNEL_USERNAME")

if not api_id or not api_hash:
    print("❌ API Credentials missing.")
    exit(1)

app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)

async def main():
    async with app:
        print(f"👤 Connected as: {(await app.get_me()).first_name}")
        
        # 1. Try to get chat directly
        print(f"\n🔍 Checking target channel: {target_id}")
        try:
            # Attempt to convert to int if it looks like one
            if str(target_id).startswith('-') or str(target_id).isdigit():
                peer = int(target_id)
            else:
                peer = target_id
                
            chat = await app.get_chat(peer)
            print(f"✅ FOUND! Title: {chat.title}")
            print(f"   ID: {chat.id}")
            print(f"   Username: @{chat.username}")
        except Exception as e:
            print(f"❌ Could not access target directly: {e}")
            
        # 2. List all dialogs to help user find the real ID
        print("\n📋 Listing joined channels/groups (Last 20):")
        count = 0
        async for dialog in app.get_dialogs(limit=20):
            chat = dialog.chat
            if chat.type.name in ['CHANNEL', 'SUPERGROUP', 'GROUP']:
                count += 1
                print(f"   🔹 {chat.title} | ID: {chat.id} | @{chat.username or 'NoUsername'}")
        
        if count == 0:
            print("   (No channels or groups found)")

        # 3. Magic ID Finder (Forward check)
        print("\n🕵️ Magic ID Finder:")
        print("   Checking your 'Saved Messages' for forwarded posts...")
        try:
            async for msg in app.get_chat_history("me", limit=1):
                if msg.forward_from_chat:
                    print("   🎉 FOUND FORWARDED MESSAGE!")
                    print(f"   From Channel: {msg.forward_from_chat.title}")
                    print(f"   ✅ Real ID: {msg.forward_from_chat.id}")
                    print(f"   (Username: @{msg.forward_from_chat.username})")
                else:
                    print("   ℹ️ The last message in 'Saved Messages' is NOT a forward.")
                    print("   Please forward a message FROM your target channel TO your 'Saved Messages'.")
        except Exception as e:
            print(f"   ❌ Error checking saved messages: {e}")

if __name__ == "__main__":
    app.run(main())
