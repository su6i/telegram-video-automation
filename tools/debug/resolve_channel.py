
import os
import sys
import asyncio
from dotenv import load_dotenv
from pyrogram import Client

# Load env to get API credentials
load_dotenv()

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
invite_link = "https://t.me/+TlX2TjG6t_I5Zjc0"

async def main():
    if not api_id or not api_hash:
        print("❌ API_ID or API_HASH missing in .env")
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
    asyncio.run(main())
