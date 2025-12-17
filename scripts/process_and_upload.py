import os
import subprocess
import sys
from telegram import Bot

# Add project root to sys.path so we can import 'src'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.error import TelegramError
from pyrogram import Client
import asyncio
import json
import re
from dotenv import load_dotenv
import math

# Import Shared Modules
from src.video_utils import (
    get_video_info,
    calculate_optimal_segments,
    process_video_for_bot_safe as process_video_for_bot,
    process_video_for_user_safe as process_video_for_user,
    split_video_for_bot_safe as split_video_for_bot,
    get_smart_title,
    SIZE_THRESHOLD_MB,
    BOT_MAX_SIZE_MB,
    USER_MAX_SIZE_MB
)
from src.telegram_utils import (
    upload_with_bot,
    upload_with_user_account,
    decide_upload_method
)

# Load environment variables from root
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))

# تنظیمات ربات
telegram_token = os.getenv("TELEGRAM_TOKEN")
channel_id = os.getenv("CHANNEL_ID")

# تنظیمات Pyrogram
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
# Use CHANNEL_USERNAME if set, otherwise fallback to CHANNEL_ID
channel_username = os.getenv("CHANNEL_USERNAME") or os.getenv("CHANNEL_ID")

# Ensure channel_username is int if it looks like an ID
if channel_username and (channel_username.startswith('-') or channel_username.isdigit()):
    try:
        channel_username = int(channel_username)
    except ValueError:
        pass

# تنظیمات پروژه
video_dir = "downloads"
output_dir = "processed"

# بررسی متغیرهای محیطی
has_bot_creds = all([telegram_token, channel_id])
# Now user creds needs API stuff + SOME target (username OR id)
has_user_creds = all([api_id, api_hash]) and (channel_username or channel_id)

if not has_bot_creds and not has_user_creds:
    raise ValueError("""
❌ تنظیمات ناقص است!
لطفاً حداقل یکی از روش‌های آپلود (ربات یا اکانت کاربری) را در فایل .env تنظیم کنید.
""")

if not has_bot_creds:
    print("⚠️ هشدار: تنظیمات ربات (TELEGRAM_TOKEN) یافت نشد. فقط امکان آپلود با اکانت کاربری وجود دارد.")

# ایجاد پوشه خروجی
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def main():
    """پردازش و آپلود ترکیبی"""
    # Initialize local flags based on global config
    bot_available = has_bot_creds
    
    processed_count = 0
    failed_count = 0
    
    # ایجاد کلاینت Pyrogram
    app = None
    if has_user_creds:
        app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)
    
    try:
        if app:
            await app.start()
            print("🔐 ورود موفق با اکانت کاربری")
            
            # Resolve Peer (Fix for PEER_ID_INVALID)
            # Ensure Pyrogram knows about the target channel
            if channel_username and isinstance(channel_username, int):
                print(f"🔍 در حال شناسایی کانال {channel_username}...")
                try:
                    await app.get_chat(channel_username)
                    print("✅ کانال شناسایی شد.")
                except Exception:
                    print("⚠️ شناسایی مستقیم ناموفق بود. جستجو در لیست گفتگوها...")
                    found = False
                    async for dialog in app.get_dialogs():
                        if dialog.chat.id == channel_username:
                            found = True
                            print(f"🎉 کانال در لیست گفتگوها پیدا شد: {dialog.chat.title}")
                            break
                    
                    if not found:
                         print("❌ هشدار: کانال در لیست شما پیدا نشد. ممکن است آپلود فیل شود.")
        
        # تست اتصال ربات
        if bot_available:
            try:
                bot = Bot(token=telegram_token)
                bot_info = await bot.get_me()
                print(f"🤖 ربات آماده: @{bot_info.username}")
            except Exception as e:
                print(f"⚠️ خطا در اتصال به ربات: {e}")
                bot_available = False # Disable bot for this run
        
        video_files = [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        video_files.sort()  # Sort by filename (001_..., 002_...)
        total_files = len(video_files)
        print(f"\n📁 تعداد کل فایل‌های ویدیویی: {total_files}")
        
        for i, filename in enumerate(video_files, 1):
            input_path = os.path.join(video_dir, filename)
            title = get_smart_title(input_path)  # استفاده از تیتر هوشمند (الویت متادیتا)
            
            print(f"\n{'='*60}")
            print(f"[{i}/{total_files}] پردازش: {title}")
            print(f"{'='*60}")
            
            if not os.path.exists(input_path):
                print(f"❌ فایل ورودی یافت نشد")
                failed_count += 1
                continue
            
            # Check if already processed
            processed_files = []
            
            output_path = os.path.join(output_dir, filename)
            
            processing_needed = True
            if os.path.exists(output_path):
                print(f"✅ فایل پردازش شده از قبل موجود است: {output_path}")
                processing_needed = False
                processed_files = [output_path]
                
                # Still need to decide method for uploading
                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                upload_method = decide_upload_method(file_size_mb)
                
                # Fallback if bot missing
                if upload_method == 'bot' and not bot_available:
                     upload_method = 'user'
            
            if processing_needed:
                file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
                upload_method = decide_upload_method(file_size_mb)
                # Fallback if bot missing
                if upload_method == 'bot' and not bot_available:
                    print(f"ℹ️ فایل کوچک ({file_size_mb:.2f}MB) است اما ربات فعال نیست. سوییچ به اکانت کاربری.")
                    upload_method = 'user'
                
                print(f"📊 اندازه فایل: {file_size_mb:.2f}MB")
                print(f"🎯 روش انتخاب شده: {'ربات' if upload_method == 'bot' else 'اکانت کاربری'}")
                
                if upload_method == "user":
                    if await process_video_for_user(input_path, output_path, title):
                        processed_files = [output_path]
                else:
                    processed_files = await split_video_for_bot(input_path, output_dir, title)
            else:
                 # Already processed case (lines ~127 in previous view)
                 # We need to re-evaluate upload method for the processed file
                 file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                 upload_method = decide_upload_method(file_size_mb)
                 if upload_method == 'bot' and not bot_available:
                    print(f"ℹ️ فایل کوچک ({file_size_mb:.2f}MB) است اما ربات فعال نیست. سوییچ به اکانت کاربری.")
                    upload_method = 'user'
                 print(f"🎯 روش انتخاب شده: {'ربات' if upload_method == 'bot' else 'اکانت کاربری'}")
            
            if not processed_files:
                print(f"❌ خطا در پردازش فایل")
                failed_count += 1
                continue
                
            # Upload Logic
            # Since the original code had complex branching for bot/user upload inside the processing block,
            # it's cleaner to separate "Processing" from "Uploading".
            
            # Helper to upload list of files
            if upload_method == "user":
                 # User usually has 1 file
                 for f_path in processed_files:
                     if await upload_with_user_account(app, f_path, title, channel_username):
                         processed_count += 1
                         print(f"🎉 آپلود با اکانت کاربری موفق!")
                     else:
                         failed_count += 1
            else:
                 # Bot
                 for j, f_path in enumerate(processed_files):
                     part_title = title if len(processed_files) == 1 else f"{title} - قسمت {j+1}/{len(processed_files)}"
                     if await upload_with_bot(f_path, part_title, telegram_token, channel_id):
                         processed_count += 1
                         print(f"🎉 آپلود با ربات موفق!")
                     else:
                         failed_count += 1
            
            # Cleanup temp files if processed freshly
            if processing_needed:
                for f_path in processed_files:
                    try:
                         # Keep the main processed file if user wants, but script usually deletes temp.
                         # User wanted to keep processed files? "mongard_videos_processed".
                         # Let's NOT delete them so user has a copy.
                         pass 
                    except:
                        pass
            
            # تأخیر بین ویدیوها
            if i < total_files:
                delay = 120 if upload_method == "user" else 30  # تأخیر بیشتر برای اکانت کاربری
                print(f"⏳ انتظار {delay} ثانیه...")
        
        print(f"\n{'='*60}")
        print(f"📊 خلاصه نتایج:")
        print(f"   📁 تعداد کل: {total_files}")
        print(f"   ✅ موفق: {processed_count}")
        print(f"   ❌ ناموفق: {failed_count}")
        print(f"   📈 درصد موفقیت: {(processed_count/total_files)*100:.1f}%")
        print(f"{'='*60}")
        
    except KeyboardInterrupt:
        print("\n⚠️ متوقف شد با Ctrl+C")
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {str(e)}")
    finally:
        await app.stop()
        print("🔒 اتصال بسته شد")

if __name__ == "__main__":
    asyncio.run(main())