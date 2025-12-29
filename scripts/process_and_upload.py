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
    process_video_for_user_safe as process_video_for_user,
    split_video_for_bot_safe as split_video_for_bot,
    split_video_for_user_safe as split_video_for_user,
    get_smart_title,
    extract_thumbnail,
    SIZE_THRESHOLD_MB,
    BOT_MAX_SIZE_MB,
    USER_MAX_SIZE_MB
)
from src.telegram_utils import (
    upload_with_bot,
    upload_with_user_account,
    decide_upload_method
)
from src.media_resolver import list_all_videos, find_video_file
from src.manifest_tracker import update_manifest_status, get_pending_videos

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

import argparse

# تنظیمات آرگومان‌ها
parser = argparse.ArgumentParser(description="Upload videos to Telegram")
parser.add_argument("--intro", action="store_true", help="Add intro to videos (default: False)")
parser.add_argument("--video-dir", type=str, help="Override video directory")
args = parser.parse_args()

# Storage directory
STORAGE_DIR = ".storage"
os.makedirs(STORAGE_DIR, exist_ok=True)
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")

def load_video_metadata(video_filename):
    """
    Parses manifest to find metadata for the given video filename.
    Handles multiple formats: 
    - 001 | Title | URL | Course | Section
    - 001_Title | URL
    - 001 | Title | URL
    """
    if not os.path.exists(MANIFEST_FILE):
        return None
        
    file_index = video_filename[:3]
    if not file_index.isdigit():
        return None

    try:
        current_course = "Unknown Course"
        current_section = "General"
        course_video_count = 0
        
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line: continue
            
            if line.startswith("# === "):
                content = line.replace("# === ", "").split(" ===")[0]
                if "(" in content:
                    current_course = content.split("(")[0].strip()
                    try:
                        count_part = content.split("(")[-1].replace(")", "").replace(" videos", "")
                        course_video_count = count_part.split(" of ")[-1] if " of " in count_part else count_part
                    except: course_video_count = "?"
                else:
                    current_course = content
                current_section = "General"
                
            elif line.startswith("## --- "):
                current_section = line.replace("## --- ", "").replace(" ---", "").strip()
                
            elif "|" in line:
                # Video Line
                clean_line = line.replace("# [DONE] ", "").strip()
                
                # Check for Match (Index can be followed by | or _)
                # Regex to match index at start
                match = re.match(rf"^{file_index}[_|\s]", clean_line)
                if match:
                    # Parse using pipe delimiter
                    parts = [p.strip() for p in clean_line.split("|")]
                    
                    url = ""
                    title = ""
                    
                    if len(parts) >= 3:
                        # Format: Index | Title | URL [| Course | Section]
                        title = parts[1]
                        url = parts[2]
                    elif len(parts) == 2:
                        # Format: Index_Title | URL
                        url = parts[1]
                        # Extract title from parts[0] which is "Index_Title"
                        title = parts[0][len(file_index):].strip("_ ")
                    
                    return {
                        "course": current_course,
                        "section": current_section,
                        "index": file_index,
                        "total": course_video_count,
                        "line_title": title,
                        "url": url
                    }
    except Exception as e:
        print(f"⚠️ Error parsing manifest: {e}")
        
    return None

# تنظیمات پروژه
UPLOAD_HISTORY_FILE = os.path.join(STORAGE_DIR, "upload_history.json")
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")

def get_index_from_filename(filename):
    return filename[:3] if filename[:3].isdigit() else filename

def load_extra_content(url):
    """
    Loads description and links from json.
    Handles lookup by key (video_url) or searching within entries (lesson_url matches).
    """
    if not os.path.exists(CONTENT_FILE):
        return None
    try:
        with open(CONTENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # 1. Direct Lookup
            if url in data:
                return data[url]
            
            # 2. Search values (In case data is keyed by lesson_url)
            for key, val in data.items():
                if val.get('video_url') == url:
                    return val
                # Also try matching course_url with the input url if it's a course page
                if val.get('course_url') == url:
                    return val
                    
            return None
    except:
        return None

def unfragment_text(text):
    """Join fragmented lines that look like they belong to the same sentence."""
    if not text: return ""
    # 1. Remove solo dots/markers that often cause false breaks
    text = re.sub(r'(?m)^\s*[\.·•]\s*$', '', text)
    
    # Pre-clean: Ensure Update markers have space
    text = re.sub(r'(?i)(?P<h>\d+/\d+ Update!|Update!|IMPORTANT:|NOTE:|WARNING:)', r'\n\n\1', text)
    
    lines = text.split('\n')
    cleaned_lines = []
    current_buffer = ""
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_buffer:
                cleaned_lines.append(current_buffer)
                current_buffer = ""
            continue
            
        if not current_buffer:
            current_buffer = stripped
        else:
            last_char = current_buffer.strip()[-1] if current_buffer.strip() else ""
            
            # PATTERN DETECTION: Should we start a NEW block?
            is_list_item = re.match(r'^(\d+\.|\-|[•·*])\s', stripped)
            is_new_header = (stripped[0].isupper() and 
                            (last_char in ".!?:;" or 
                             len(current_buffer.strip()) < 40 or # Short title before it?
                             re.match(r'^[A-Z\d\s/]+$', stripped) # All caps header?
                            ))
            
            # Decide if we should join or break
            # Join ONLY ONLY if it's very likely a sentence continuation
            if not is_list_item and not is_new_header and (last_char not in ".!?:;"):
                current_buffer += " " + stripped
            else:
                cleaned_lines.append(current_buffer)
                current_buffer = stripped
                
    if current_buffer:
        cleaned_lines.append(current_buffer)
        
    # Join with DOUBLE NEWLINES per user request for "breathable" layout
    result = '\n\n'.join(cleaned_lines).strip()
    return result

def save_upload_history(index, title, message_obj, is_bot):
    """Saves upload result to json file."""
    data = {}
    if os.path.exists(UPLOAD_HISTORY_FILE):
        try:
            with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
            
    msg_id = message_obj.message_id if is_bot else message_obj.id
    
    # Construct Link
    # Pyrogram: .link (might be None for private)
    # Bot: .link (might be None)
    link = getattr(message_obj, "link", None)
    
    # Fallback link construction for private channels
    if not link:
        # User defined channel_username might be ID (int) or username (str)
        # If it's ID like -1001234567890 -> t.me/c/1234567890/MSG_ID
        c_id = str(channel_id) # Global var from env
        if c_id.startswith("-100"):
            c_hash = c_id[4:]
            link = f"https://t.me/c/{c_hash}/{msg_id}"
        elif c_id.startswith("@"):
            link = f"https://t.me/{c_id[1:]}/{msg_id}"
            
    data[index] = {
        "title": title,
        "msg_id": msg_id,
        "link": link,
        "type": "bot" if is_bot else "user"
    }
    
    with open(UPLOAD_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Use env VIDEO_DIR if set, otherwise default to "downloads"
default_video_dir = os.getenv("VIDEO_DIR", "downloads")
video_dir = args.video_dir if args.video_dir else default_video_dir

# Use env PROCESSED_DIR if set, otherwise default to "processed"
output_dir = os.getenv("PROCESSED_DIR", "processed")

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

if not os.path.exists(video_dir):
    # Try creating it if it doesn't exist? Or just warn?
    # Better to warn if it's the custom path
    print(f"⚠️ Video directory not found: {video_dir}")
    # os.makedirs(video_dir) # Maybe don't create it, user should provide content.

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
            print("\n🚨 IMPORTANT: When asked for login, please enter your PHONE NUMBER (not Bot Token)!")
            print("   اگر از شما شماره خواسته شد، شماره موبایل خود را وارد کنید.")
            print("   اگر توکن ربات وارد کنید، برنامه کار نخواهد کرد.\n")
            
            await app.start()
            
            # Verify we are NOT a bot
            if app.me.is_bot:
                raise ValueError("❌ شما به جای شماره موبایل، توکن ربات وارد کردید! لطفاً سشن را پاک کرده و دوباره با شماره لاگین کنید.")
                
            print(f"🔐 ورود موفق با اکانت کاربری: {app.me.first_name}")
            
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
        
        # Scan all configured media paths instead of single video_dir
        print(f"\n🔍 درحال اسکن تمام مسیرهای مدیا...")
        video_files = []
        video_paths = {}  # Map filename -> full_path
        
        for filename, full_path in list_all_videos():
            video_files.append(filename)
            video_paths[filename] = full_path
        
        video_files.sort()  # Sort by filename (001_..., 002_...)
        total_files = len(video_files)
        print(f"📁 تعداد کل فایل‌های ویدیویی: {total_files}")
        
        # Load history
        history_data = {}
        if os.path.exists(UPLOAD_HISTORY_FILE):
             try:
                 with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                     history_data = json.load(f)
             except:
                 pass

        for i, filename in enumerate(video_files, 1):
            input_path = video_paths[filename]
            
            # Check history
            idx = get_index_from_filename(filename)
            if idx in history_data:
                # Optional: Verify it was successful? Assume yes if in history.
                print(f"⏩ قبلاً آپلود شده است (Skipping): {filename}")
                continue

            title = get_smart_title(input_path)  # استفاده از تیتر هوشمند (الویت متادیتا)
            
            # Load Rich Metadata
            meta = load_video_metadata(filename)
            caption = title
            full_desc = ""
            need_overflow = False
            
            if meta:
                # HEADER (Professional Bold Format)
                header_parts = [f"**{meta['course']}**"]
                if meta['section'] and meta['section'] != "General":
                    header_parts.append(f"**{meta['section']}**")
                
                final_title = meta['line_title'] if meta['line_title'] else title
                header_parts.append(f"**{meta['index']} - {final_title}**")
                
                caption = "\n".join(header_parts) + "\n\n"
                
                # Add Extra Content (Description + Links)
                extra = load_extra_content(meta['url'])
                if extra:
                    # 🔗 LINKS
                    if extra.get('links'):
                        caption += "🔗 **Links:**\n"
                        for link in extra['links']:
                            link_text = link['text']
                            # Clean "CLICK HERE" or ": CLICK HERE"
                            link_text = re.sub(r'(?i):\s*CLICK\s*HERE', '', link_text)
                            link_text = re.sub(r'(?i)CLICK\s*HERE', '', link_text)
                            link_text = link_text.strip(": ")
                            if not link_text: link_text = "Link"
                            caption += f"• [{link_text}]({link['url']})\n"
                        caption += "\n"
                    
                    # 📝 INFO (Cleaned Description)
                    if extra.get('description'):
                        desc = extra['description']
                        
                        # --- ROBUST COMMENT STRIPPING (Telegram Output Only) ---
                        desc = re.split(r'(?i)Comments\s*\n\s*\d+', desc)[0]
                        desc = re.split(r'(?i)Post Comment', desc)[0]
                        desc = re.split(r'(?i)\n\d+\s+Comments', desc)[0]
                        
                        # Timestamped replies (e.g. "Amer Tobing\n20 hours ago\n...")
                        desc = re.split(r'(?m)^\d+ (minutes|hours|days|weeks|months) ago', desc)[0]
                        desc = re.split(r'(?m)^REPLY\s*\n', desc)[0]
                        
                        desc = desc.strip()
                        
                        # Remove placeholder dots used for spacing
                        desc = re.sub(r'(?m)^\.\s*$', '', desc)
                        # Fix spacing before headers
                        desc = re.sub(r'(?i)(?P<h>QUICK UPDATE:|IMPORTANT:|NOTE:|WARNING:)', r'\n\n**\1**', desc)
                        # Format Update Headers
                        desc = re.sub(r'(^|\n)(\d{1,2}/\d{1,2} Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
                        desc = re.sub(r'(^|\n)(Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
                        
                        # 1. Clean labels first to reveal actual punctuation
                        desc = re.sub(r'(?i)CLICK\s*HERE\s*:?\s*', '', desc)
                        
                        # 2. Unfragment (Joins sentences, respects lists)
                        desc = unfragment_text(desc)
                        
                        # Final cleanliness check
                        desc = re.sub(r'\n{3,}', '\n\n', desc).strip()
                        
                        if desc:
                            current_len = len(caption) + len("📝 **Info:**\n")
                            remaining = 1024 - current_len - 20

                            if len(desc) <= remaining:
                                caption += f"📝 **Info:**\n{desc}"
                            else:
                                candidate = desc[:remaining]
                                last_break = max(candidate.rfind('\n\n'), candidate.rfind('\n'), candidate.rfind('. '))
                                
                                if last_break > 0:
                                    visible = desc[:last_break+1].strip()
                                    overflow_text = desc[last_break+1:].strip()
                                    caption += f"📝 **Info:**\n{visible}\n\n⬇️ **(See next message)**"
                                    need_overflow = True
                                else:
                                    caption += f"📝 **Info:**\n{candidate}..."
                                    overflow_text = desc[remaining:]
                                    need_overflow = True
            else:
                # Fallback for when no metadata is found
                caption = f"**{title}**"


            print(f"\n{'='*60}")
            print(f"[{i}/{total_files}] پردازش: {title}")
            print(f"📄 Generated Caption Preview:\n{caption[:200]}...")
            if meta:
                print(f"   ℹ️ Metadata: {meta['course']} | {meta['section']}")
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
                print(f"🔄 Processing and Compressing to 720p...")
                
                # Step 1: Always process & compress to 720p first
                # This generates 'output_path' which is the 720p version
                success = await process_video_for_user(input_path, output_path, title, add_intro=args.intro)
                
                if success and os.path.exists(output_path):
                    # Step 2: Check size of the COMPRESSED file
                    compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    print(f"📉 Compressed Size: {compressed_size_mb:.2f}MB")
                    
                    upload_method = 'user' # Default for large files
                    
                    # Decide if we need to split based on COMPRESSED size
                    if compressed_size_mb > USER_MAX_SIZE_MB:
                        print(f"⚠️ Still larger than {USER_MAX_SIZE_MB}MB after compression. Splitting...")
                        # Split the ALREADY PROCESSED file
                        # We pass 'add_intro=False' because we already added intro in Step 1 (if any)
                        # We pass output_path as input to split
                        processed_files = await split_video_for_user(output_path, output_dir, title, target_size_mb=USER_MAX_SIZE_MB, add_intro=False)
                        
                        # We can remove the big processed file since we have parts now
                        try:
                            # os.remove(output_path) # Optional: remove 720p single file to save space? 
                            # But wait, logic later cleans up 'processed_files'. 
                            # Valid point: Keep it for simple cleanup logic later.
                            pass
                        except: pass
                    else:
                        # Fits in one part
                        processed_files = [output_path]
                        
                        # Check if small enough for bot? (Optional)
                        # If < 50MB, user might want bot? But user said "speed up upload", user account is fine.
                        # Let's stick to User Account for consistency unless requested.
                else:
                    print("❌ Processing failed.")
                    failed_count += 1
                    continue
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
            thumb_path = os.path.join(output_dir, f"thumb_{idx}.jpg")
            has_thumb = False
            
            if processed_files:
                # Try 5 seconds in, then 10 if that might be better? 5 is usually safe.
                # Extract thumb from the FIRST processed part
                print(f"🖼️ Extracting representative thumbnail from {os.path.basename(processed_files[0])}...")
                has_thumb = extract_thumbnail(processed_files[0], thumb_path, timestamp="00:00:05")

            if upload_method == "user":
                 # User usually has 1 file
                 for f_path in processed_files:
                     msg = await upload_with_user_account(app, f_path, caption, channel_username, thumb=thumb_path if has_thumb else None)
                     if msg:
                         processed_count += 1
                         print(f"🎉 آپلود با اکانت کاربری موفق!")
                         # Save History & Update Manifest
                         idx = get_index_from_filename(filename)
                         save_upload_history(idx, title, msg, False)
                         # Update manifest with status
                         msg_id = msg.id if hasattr(msg, 'id') else None
                         update_manifest_status(idx, "UPLOADED", msg_id=msg_id)
                         
                         # Send Overflow Message if needed
                         if need_overflow and overflow_text:
                             print("   📄 Description split. Sending remainder as reply...")
                             try:
                                 await app.send_message(
                                     chat_id=channel_username,
                                     text=f"📄 **Continued:**\n\n{overflow_text}",
                                     reply_to_message_id=msg.id,
                                     disable_web_page_preview=True
                                 )
                                 print("   ✅ Overflow message sent.")
                             except Exception as exc:
                                 print(f"   ⚠️ Failed to send overflow: {exc}")
                     else:
                         failed_count += 1
                         idx = get_index_from_filename(filename)
                         update_manifest_status(idx, "FAILED")
            else:
                 # Bot
                 for j, f_path in enumerate(processed_files):
                     part_caption = caption if len(processed_files) == 1 else f"{caption}\n(Part {j+1}/{len(processed_files)})"
                     msg = await upload_with_bot(f_path, part_caption, telegram_token, channel_id, thumb=thumb_path if has_thumb else None)
                     if msg:
                         processed_count += 1
                         print(f"🎉 آپلود با ربات موفق!")
                         # Save History & Update Manifest
                         if j == 0:  # Only update for first part
                            idx = get_index_from_filename(filename)
                            save_upload_history(idx, title, msg, True)
                            msg_id = msg.message_id if hasattr(msg, 'message_id') else None
                            update_manifest_status(idx, "UPLOADED", msg_id=msg_id)
                     else:
                         failed_count += 1
                         if j == 0:
                            idx = get_index_from_filename(filename)
                            update_manifest_status(idx, "FAILED")
            
            # Cleanup thumb
            if has_thumb and os.path.exists(thumb_path):
                try: os.remove(thumb_path)
                except: pass
            
            # Cleanup temp files
            if processing_needed: 
                print("🧹 Cleaning up temporary files...")
                for f_path in processed_files:
                    try:
                        if os.path.exists(f_path):
                            os.remove(f_path)
                            print(f"   🗑️ Removed: {os.path.basename(f_path)}")
                    except Exception as e:
                        print(f"   ⚠️ Cleanup failed for {f_path}: {e}")
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