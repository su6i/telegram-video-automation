import argparse
import asyncio
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

# Load env to get API credentials
load_dotenv(env_path())

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

async def main(invite_link):
    if not api_id or not api_hash:
        print("❌ API_ID or API_HASH missing in .env")
        return
    if not invite_link:
        print("❌ Usage: resolve_channel.py <invite-link>  (or set CHANNEL_INVITE_LINK)")
        return

    print("🔐 Connecting to Telegram...")
    app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)
    
    async with app:
        print(f"🔍 Resolving invite link: {invite_link}")
        try:
            # removing https://t.me/+ prefix if needed, but join_chat handles URLs usually
            chat = await app.join_chat(invite_link)
            print(f"✅ Successfully joined/resolved chat: {chat.title}")
            print(f"🆔 CHAT ID: {chat.id}")
            
            # Print for parsing
            print(f"RESULT_ID={chat.id}")
            
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                print("⚠️ User already joined. Fetching content...")
                # Try getting chat by preview or just iterating dialogs? 
                # Identifying a private chat by link is hard if we don't know the ID.
                # But joining usually returns the CHAT info in the error? No.
                
                # Try get_chat with the link? (Works if member)
                try:
                    chat = await app.get_chat(invite_link)
                    print(f"✅ Resolved chat via get_chat: {chat.title}")
                    print(f"🆔 CHAT ID: {chat.id}")
                except:
                    # Iterate dialogs and look for one with the same link (impossible)
                    # Look for title? We don't know the title.
                    # Best bet: The user just joined it? 
                    # Let's list the top 5 dialogs and let user identify?
                    print("\n📋 Listing recent dialogs (Find your channel here):")
                    async for dialog in app.get_dialogs(limit=10):
                        print(f"   - {dialog.chat.title} | ID: {dialog.chat.id} | Type: {dialog.chat.type}")
            else:
                print(f"❌ Error resolving link: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve a Telegram invite link to a chat id.")
    # The invite link grants access to a private channel, so it is an argument,
    # never a committed literal (rule 035).
    parser.add_argument("invite_link", nargs="?", default=os.getenv("CHANNEL_INVITE_LINK", ""), help="Invite link to resolve; falls back to CHANNEL_INVITE_LINK from .env")
    args = parser.parse_args()

    asyncio.run(main(args.invite_link))
