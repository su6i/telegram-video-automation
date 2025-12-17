import os
import subprocess
from telegram import Bot
from telegram.error import TelegramError
from pyrogram import Client
import asyncio
import json
import re
from dotenv import load_dotenv
import math
from datetime import datetime, timedelta

# Import Shared Modules
from src.video_utils import (
    get_video_info,
    calculate_optimal_segments,
    process_video_for_bot_safe,
    process_video_for_user_safe,
    split_video_for_bot_safe,
    normalize_title,
    SIZE_THRESHOLD_MB,
    BOT_MAX_SIZE_MB,
    USER_MAX_SIZE_MB
)
from src.telegram_utils import (
    upload_with_bot,
    upload_with_user_account,
    decide_upload_method
)

# لود متغیرهای محیطی از .env
load_dotenv()

# تنظیمات ربات
telegram_token = os.getenv("TELEGRAM_TOKEN")
channel_id = os.getenv("CHANNEL_ID")

# تنظیمات Pyrogram
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
channel_username = os.getenv("CHANNEL_USERNAME")

# تنظیمات
processed_dir = "processed"
json_log_file = "upload_log.json"

# بررسی متغیرهای محیطی
required_vars = [telegram_token, channel_id, api_id, api_hash, channel_username]
if not all(required_vars):
    raise ValueError("""
لطفاً متغیرهای زیر را در فایل .env تنظیم کنید:
- TELEGRAM_TOKEN (برای ربات)
- CHANNEL_ID (برای ربات)  
- API_ID (برای اکانت کاربری)
- API_HASH (برای اکانت کاربری)
- CHANNEL_USERNAME (برای اکانت کاربری - مثل @mychannel)
""")

# ایجاد پوشه خروجی
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def get_channel_videos(app):
    """دریافت لیست ویدیوهای موجود در کانال"""
    try:
        print("📋 دریافت لیست ویدیوهای کانال...")
        
        uploaded_videos = set()
        message_count = 0
        
        # دریافت پیام‌های کانال (آخرین 1000 پیام)
        async for message in app.get_chat_history(channel_username, limit=1000):
            message_count += 1
            
            if message.video and message.caption:
                # نرمال‌سازی عنوان
                normalized_caption = normalize_title(message.caption)
                uploaded_videos.add(normalized_caption)
                
                # بررسی قسمت‌های مختلف (برای ویدیوهای تقسیم شده)
                if " - قسمت " in message.caption:
                    base_title = message.caption.split(" - قسمت ")[0]
                    normalized_base = normalize_title(base_title)
                    uploaded_videos.add(normalized_base)
            
            # نمایش پیشرفت
            if message_count % 100 == 0:
                print(f"   📊 بررسی شده: {message_count} پیام")
        
        print(f"✅ تعداد ویدیوهای یافت شده در کانال: {len(uploaded_videos)}")
        print(f"📊 تعداد کل پیام‌های بررسی شده: {message_count}")
        
        return uploaded_videos
        
    except Exception as e:
        print(f"❌ خطا در دریافت لیست کانال: {str(e)}")
        return set()

def get_local_videos():
    """دریافت لیست ویدیوهای محلی"""
    try:
        video_files = []
        for filename in os.listdir(video_dir):
            if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                title = os.path.splitext(filename)[0]
                normalized_title = normalize_title(title)
                video_files.append({
                    'filename': filename,
                    'title': title,
                    'normalized_title': normalized_title,
                    'path': os.path.join(video_dir, filename),
                    'size_mb': os.path.getsize(os.path.join(video_dir, filename)) / (1024 * 1024)
                })
        
        print(f"📁 تعداد فایل‌های محلی: {len(video_files)}")
        return video_files
        
    except Exception as e:
        print(f"❌ خطا در خواندن فایل‌های محلی: {str(e)}")
        return []

def find_missing_videos(local_videos, uploaded_videos):
    """یافتن ویدیوهای آپلود نشده"""
    missing_videos = []
    
    for video in local_videos:
        if video['normalized_title'] not in uploaded_videos:
            missing_videos.append(video)
            
    print(f"🔍 ویدیوهای آپلود نشده: {len(missing_videos)}")
    
    if missing_videos:
        print("\n📝 لیست ویدیوهای آپلود نشده:")
        for i, video in enumerate(missing_videos, 1):
            print(f"   {i:2d}. {video['title']} ({video['size_mb']:.1f}MB)")
    
    return missing_videos


async def retry_failed_uploads():
    """آپلود مجدد فایل‌های ناموفق"""
    processed_count = 0
    failed_count = 0
    
    # ایجاد کلاینت Pyrogram
    app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)
    
    try:
        await app.start()
        print("🔐 ورود موفق با اکانت کاربری")
        
        # تست اتصال ربات
        bot = Bot(token=telegram_token)
        bot_info = await bot.get_me()
        print(f"🤖 ربات آماده: @{bot_info.username}")
        
        # مرحله 1: دریافت لیست ویدیوهای کانال
        uploaded_videos = await get_channel_videos(app)
        
        # مرحله 2: دریافت لیست فایل‌های محلی
        local_videos = get_local_videos()
        
        # مرحله 3: یافتن فایل‌های آپلود نشده
        missing_videos = find_missing_videos(local_videos, uploaded_videos)
        
        if not missing_videos:
            print("🎉 همه فایل‌ها قبلاً آپلود شده‌اند!")
            return
        
        print(f"\n🔄 شروع آپلود مجدد {len(missing_videos)} فایل...")
        
        # مرحله 4: آپلود فایل‌های باقی‌مانده
        for i, video in enumerate(missing_videos, 1):
            title = video['title']
            input_path = video['path']
            file_size_mb = video['size_mb']
            
            print(f"\n{'='*60}")
            print(f"[{i}/{len(missing_videos)}] آپلود مجدد: {title}")
            print(f"{'='*60}")
            
            upload_method = decide_upload_method(file_size_mb)
            
            print(f"📊 اندازه فایل: {file_size_mb:.2f}MB")
            print(f"🎯 روش انتخاب شده: {'ربات' if upload_method == 'bot' else 'اکانت کاربری'}")
            
            if upload_method == "bot":
                # استفاده از ربات
                if file_size_mb <= SIZE_THRESHOLD_MB:
                    # فایل کوچک - پردازش مستقیم
                    output_path = os.path.join(output_dir, f"bot_{video['filename']}")
                    success = await process_video_for_bot_safe(input_path, output_path, title)
                    
                    if success:
                        upload_success = await upload_with_bot(output_path, title, telegram_token, channel_id)
                        if upload_success:
                            processed_count += 1
                            print(f"🎉 آپلود با ربات موفق!")
                        else:
                            failed_count += 1
                        
                        # حذف فایل موقت
                        try:
                            os.remove(output_path)
                        except:
                            pass
                    else:
                        failed_count += 1
                else:
                    # فایل بزرگ - تقسیم برای ربات
                    output_files = await split_video_for_bot_safe(input_path, output_dir, title)
                    
                    if output_files:
                        upload_success_count = 0
                        for j, output_file in enumerate(output_files):
                            part_title = f"{title} - قسمت {j+1}/{len(output_files)}"
                            
                            if await upload_with_bot(output_file, part_title, telegram_token, channel_id):
                                upload_success_count += 1
                            
                            try:
                                os.remove(output_file)
                            except:
                                pass
                            
                            if j < len(output_files) - 1:
                                await asyncio.sleep(5)  # تأخیر کوتاه بین قسمت‌ها
                        
                        if upload_success_count == len(output_files):
                            processed_count += 1
                            print(f"🎊 تمام قسمت‌ها با ربات آپلود شد!")
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
            
            else:
                # استفاده از اکانت کاربری
                output_path = os.path.join(output_dir, f"user_{video['filename']}")
                success = await process_video_for_user_safe(input_path, output_path, title)
                
                if success:
                    upload_success = await upload_with_user_account(app, output_path, title, channel_username)
                    if upload_success:
                        processed_count += 1
                        print(f"🎉 آپلود با اکانت کاربری موفق!")
                    else:
                        failed_count += 1
                    
                    # حذف فایل موقت
                    try:
                        os.remove(output_path)
                    except:
                        pass
                else:
                    failed_count += 1
            
            # تأخیر بین ویدیوها
            if i < len(missing_videos):
                delay = 120 if upload_method == "user" else 30
                print(f"⏳ انتظار {delay} ثانیه...")
                await asyncio.sleep(delay)
        
        print(f"\n{'='*60}")
        print(f"📊 خلاصه نتایج آپلود مجدد:")
        print(f"   📁 فایل‌های باقی‌مانده: {len(missing_videos)}")
        print(f"   ✅ موفق: {processed_count}")
        print(f"   ❌ ناموفق: {failed_count}")
        print(f"   📈 درصد موفقیت: {(processed_count/len(missing_videos))*100:.1f}%")
        print(f"{'='*60}")
        
        # نمایش فایل‌های باقی‌مانده
        if failed_count > 0:
            print(f"\n⚠️ فایل‌هایی که هنوز آپلود نشده‌اند ممکن است نیاز به بررسی دستی داشته باشند.")
        
    except KeyboardInterrupt:
        print("\n⚠️ متوقف شد با Ctrl+C")
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {str(e)}")
    finally:
        await app.stop()
        print("🔒 اتصال بسته شد")

if __name__ == "__main__":
    print("🔄 شروع آپلود مجدد فایل‌های ناموفق...")
    asyncio.run(retry_failed_uploads())