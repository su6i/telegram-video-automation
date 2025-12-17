import os
import asyncio
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("TELEGRAM_TOKEN")

async def check_bot_access():
    """بررسی دسترسی bot به کانال"""
    app = Client("bot_checker", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
    
    try:
        await app.start()
        print("🤖 Bot متصل شد")
        
        # لیست Channel ID های مختلف برای تست
        channel_ids = [
            "-1002564396763",
            "-2564396763",
            "1002564396763",
            "2564396763"
        ]
        
        for channel_id in channel_ids:
            print(f"\n🔍 تست کانال: {channel_id}")
            try:
                # تلاش برای دریافت اطلاعات کانال
                chat_info = await app.get_chat(int(channel_id))
                print(f"✅ موفق: {chat_info.title} - نوع: {chat_info.type}")
                
                # بررسی عضویت bot
                try:
                    member = await app.get_chat_member(int(channel_id), "me")
                    print(f"🔑 وضعیت bot: {member.status}")
                except Exception as e:
                    print(f"⚠️ خطا در بررسی عضویت: {str(e)}")
                
                # تست دریافت پیام‌ها
                try:
                    message_count = 0
                    async for message in app.get_chat_history(int(channel_id), limit=5):
                        message_count += 1
                        if message.video:
                            print(f"📹 ویدیو یافت شد: {message.caption[:50] if message.caption else 'بدون کپشن'}...")
                    print(f"📊 تعداد پیام‌های تست شده: {message_count}")
                except Exception as e:
                    print(f"❌ خطا در دریافت پیام‌ها: {str(e)}")
                    
            except Exception as e:
                print(f"❌ خطا: {str(e)}")
        
        # تست با username اگر دارید
        print(f"\n📝 اگر username کانال دارید، آن را وارد کنید (یا Enter بزنید):")
        username = input("Username کانال (مثل @mychannel): ").strip()
        
        if username:
            try:
                chat_info = await app.get_chat(username)
                print(f"✅ کانال با username: {chat_info.title} - ID: {chat_info.id}")
            except Exception as e:
                print(f"❌ خطا با username: {str(e)}")
        
    except Exception as e:
        print(f"❌ خطای کلی: {str(e)}")
    finally:
        await app.stop()

if __name__ == "__main__":
    asyncio.run(check_bot_access())