import os
import asyncio
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("TELEGRAM_TOKEN")

async def check_bot_access():
    """Check bot access to channel"""
    app = Client("bot_checker", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    
    try:
        await app.start()
        print("🤖 Bot connected")
        # List of different channel IDs for testing
        channel_ids = [
            "-1002564396763",
            "-2564396763",
            "1002564396763",
            "2564396763"
        ]
        
        for channel_id in channel_ids:
            print(f"\n🔍 Testing channel: {channel_id}")
            try:
                # Attempt to get channel info
                chat_info = await app.get_chat(int(channel_id))
                print(f"✅ Success: {chat_info.title} - Type: {chat_info.type}")
                
                # Check bot membership
                try:
                    member = await app.get_chat_member(int(channel_id), "me")
                    print(f"🔑 Bot Status: {member.status}")
                except Exception as e:
                    print(f"⚠️ Membership check error: {str(e)}")
                
                # Test fetching messages
                try:
                    message_count = 0
                    async for message in app.get_chat_history(int(channel_id), limit=5):
                        message_count += 1
                        if message.video:
                            print(f"📹 Video found: {message.caption[:50] if message.caption else 'No caption'}...")
                    print(f"📊 Messages checked: {message_count}")
                except Exception as e:
                    print(f"❌ Error fetching messages: {str(e)}")
                    
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        
        # Test with username if available
        print(f"\n📝 If you have channel username, enter it here (or press Enter to skip):")
        username = input("Channel Username (e.g. @mychannel): ").strip()
        
        if username:
            try:
                chat_info = await app.get_chat(username)
                print(f"✅ Channel with username: {chat_info.title} - ID: {chat_info.id}")
            except Exception as e:
                print(f"❌ Error with username: {str(e)}")
        
    except Exception as e:
        print(f"❌ General Error: {str(e)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(check_bot_access())