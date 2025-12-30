import os
import subprocess
import sys
import asyncio
import json
import re
import math
import argparse
import getpass
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from telegram import Bot
from telegram.error import TelegramError
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import PasswordHashInvalid, SessionPasswordNeeded, PhoneCodeInvalid

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Shared Modules
from src.video_utils import (
    process_video_for_user_safe as process_video_for_user,
    split_video_for_bot_safe as split_video_for_bot,
    split_video_for_user_safe as split_video_for_user,
    get_smart_title,
    extract_thumbnail,
    is_video_valid,
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
from src.manifest_tracker import update_manifest_status, get_pending_videos, get_all_manifest_videos

# Load environment variables
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(root_dir, ".env"))

# Bot Config
telegram_token = os.getenv("TELEGRAM_TOKEN")
channel_id = os.getenv("CHANNEL_ID")

# Pyrogram Config
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
# Use CHANNEL_USERNAME if set, otherwise fallback to CHANNEL_ID
channel_username = os.getenv("CHANNEL_USERNAME") or os.getenv("CHANNEL_ID")

# Ensure channel_username is int if it looks like an ID
if channel_username and (isinstance(channel_username, str) and (channel_username.startswith('-') or channel_username.isdigit())):
    try:
        channel_username = int(channel_username)
    except ValueError:
        pass

# Argument Config
parser = argparse.ArgumentParser(description="Upload videos to Telegram")
parser.add_argument("--intro", action="store_true", help="Add intro to videos (default: False)")
parser.add_argument("--video-dir", type=str, help="Override video directory")
parser.add_argument("--res", type=int, choices=[720, 1080], default=720, help="Target resolution (720 or 1080, default: 720)")
parser.add_argument("--index-offset", type=int, default=0, help="Skip N messages before starting index (default: 0)")
parser.add_argument("--force-user", action="store_true", help="Force using user account (hybrid_account) for indexing")
parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually uploading")
parser.add_argument("--cleanup", action="store_true", help="Remove processed files after successful upload")
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

# Project Config
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
    """
    Join fragmented lines that look like they belong to the same sentence.
    Improved: Better handles cases like 'select\nSettings' -> 'select Settings'
    """
    if not text: return ""
    
    # 1. Remove solo dots/markers that often cause false breaks
    text = re.sub(r'(?m)^\s*[\.·•]\s*$', '', text)
    
    # Pre-clean: Ensure Update/Important markers have space before them
    text = re.sub(r'(?i)(?P<h>\d+/\d+ Update!|Update!|IMPORTANT:|NOTE:|WARNING:|QUICK UPDATE:)', r'\n\n\1', text)
    
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
            is_list_item = re.match(r'^(\d+\.|[\-•·*])\s+\S', stripped)  # Must have content after marker
            
            # Is this line a standalone header? (Usually ALL CAPS or ends with colon)
            is_header = (re.match(r'^[A-Z][A-Z\s]+:?$', stripped) or  # ALL CAPS
                        stripped.endswith(':'))
            
            # Is this a short continuation? (Like "Settings" after "select")
            is_short_continuation = (len(stripped) < 30 and 
                                    not is_header and 
                                    not is_list_item and
                                    last_char not in ".!?")
            
            # IMPROVED: Join more aggressively for short lines
            # Only break if: ends with sentence-ending punctuation OR is a list/header
            should_join = (is_short_continuation or 
                          (last_char not in ".!?:;" and not is_list_item and not is_header))
            
            if should_join:
                current_buffer += " " + stripped
            else:
                cleaned_lines.append(current_buffer)
                current_buffer = stripped
                
    if current_buffer:
        cleaned_lines.append(current_buffer)
        
    # Join with DOUBLE NEWLINES for "breathable" layout
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

# Environment Validation
has_bot_creds = all([telegram_token, channel_id])
# Now user creds needs API stuff + SOME target (username OR id)
has_user_creds = all([api_id, api_hash]) and (channel_username or channel_id)

if not has_bot_creds and not has_user_creds:
    raise ValueError("""
❌ Incomplete configuration!
Please set at least one upload method (Bot or User Account) in .env file.
""")

if not has_bot_creds:
    print("⚠️ Warning: Bot token (TELEGRAM_TOKEN) not found. Only User Account upload is possible.")

# Create output directory
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

if not os.path.exists(video_dir):
    # Try creating it if it doesn't exist? Or just warn?
    # Better to warn if it's the custom path
    print(f"⚠️ Video directory not found: {video_dir}")
    # os.makedirs(video_dir) # Maybe don't create it, user should provide content.

async def main():
    """Combined Processing and Upload Flow"""
    # Initialize local flags based on global config
    bot_available = has_bot_creds
    
    processed_count = 0
    failed_count = 0
    
    # Create Pyrogram Client
    app = None
    if has_user_creds:
        app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)
    
    try:
        if app:
            print("\n🚨 IMPORTANT: When asked for login, please enter your PHONE NUMBER (not Bot Token)!")
            print("   If prompted for a phone number, please enter it.")
            print("   If you enter a Bot Token, the program will NOT work.\n")
            
            try:
                await app.start()
            except SessionPasswordNeeded:
                print("🔐 Two-Step Verification is enabled.")
                for _ in range(3):
                    pw = getpass.getpass("🔑 Enter your 2FA Password: ")
                    try:
                        await app.check_password(pw)
                        break
                    except AuthPasswordInvalid:
                        print("❌ Incorrect password. Please try again.")
                else:
                    print("❌ Too many failed attempts.")
                    return
            except Exception as e:
                print(f"❌ Login failed: {e}")
                return
                
            # Verify we are NOT a bot
            if app.me.is_bot:
                raise ValueError("❌ You entered a Bot Token instead of a Phone Number! Please delete the session and login with your phone.")
                
            print(f"🔐 Successfully logged in with user account: {app.me.first_name}")
            
            # Resolve Peer (Fix for PEER_ID_INVALID)
            # Ensure Pyrogram knows about the target channel
            if channel_username and isinstance(channel_username, int):
                print(f"🔍 Identifying channel {channel_username}...")
                try:
                    await app.get_chat(channel_username)
                    print("✅ Channel identified.")
                except Exception:
                    print("⚠️ Direct identification failed. Searching in dialogs...")
                    found = False
                    async for dialog in app.get_dialogs():
                        if dialog.chat.id == channel_username:
                            found = True
                            print(f"🎉 Channel found in dialogs: {dialog.chat.title}")
                            break
                    
                    if not found:
                         print("❌ Warning: Channel not found in your dialogs. Upload may fail.")
        
        # Test Bot Connection
        if bot_available:
            try:
                bot = Bot(token=telegram_token)
                bot_info = await bot.get_me()
                print(f"🤖 Bot Ready: @{bot_info.username}")
            except Exception as e:
                print(f"⚠️ Error connecting to bot: {e}")
                bot_available = False # Disable bot for this run
        
        # 1. Scan available physical files once
        print(f"\n🔍 Scanning all media paths...")
        physical_videos = {} # Map index -> (filename, full_path)
        
        for filename, full_path in list_all_videos():
            idx = get_index_from_filename(filename)
            if idx.isdigit():
                physical_videos[idx] = (filename, full_path)
        
        # 2. Get the master sequence from manifest
        manifest_videos = get_all_manifest_videos()
        if not manifest_videos:
            print("❌ Error: Manifest is empty or not found.")
            return

        total_files = len(manifest_videos)
        print(f"📁 Total videos defined in manifest: {total_files}")
        
        # Load history
        history_data = {}
        if os.path.exists(UPLOAD_HISTORY_FILE):
             try:
                 with open(UPLOAD_HISTORY_FILE, "r", encoding="utf-8") as f:
                     history_data = json.load(f)
             except:
                 pass

        # 2.5 Handle One-Time Placeholders for Index 001
        is_first_upload = any(v['index'] == '001' for v in manifest_videos if not v['is_done'] and v['index'] not in history_data)
        
        if is_first_upload:
            # Check history to see if we've EVER uploaded anything to this channel via this script
            if not history_data:
                res_count = 15
                print(f"\n🆕 First run detected! Reserving {res_count} messages for Index (Table of Contents)...")
                for p in range(1, res_count + 1):
                    try:
                        placeholder_text = (
                            f"📍 **Index Reserved #{p}**\n"
                            f"This message will be automatically updated with the video list.\n"
                            f"Please do not delete it to maintain the Table of Contents sequence."
                        )
                        if bot_available:
                            await bot.send_message(chat_id=channel_id, text=placeholder_text)
                        else:
                            await app.send_message(chat_id=channel_username, text=placeholder_text)
                        print(f"   ✅ Reserved {p}/{res_count}...")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        print(f"   ⚠️ Failed to reserve placeholder {p}: {e}")
                print("🏁 Index reservation complete.\n")

        # 3. Iterate through manifest sequence
        for i, m_video in enumerate(manifest_videos, 1):
            idx = m_video['index']
            
            # Skip if already done
            if m_video['is_done'] or idx in history_data:
                # print(f"⏩ {idx} already uploaded (Skipping)")
                continue

            # CRITICAL: Next video MUST exist
            if idx not in physical_videos:
                print(f"\n{'!'*60}")
                print(f"❌ Error: File for next video ({idx}) not found!")
                print(f"   Title: {m_video['title']}")
                print(f"\n   ⚠️ Possible cause: The drive containing this file is not connected.")
                print(f"   ⚠️ Program halted to maintain sequence in Telegram.")
                print(f"{'!'*60}\n")
                return # HALT

            filename, input_path = physical_videos[idx]

            title = get_smart_title(input_path)  # Use smart title (metadata preference)
            
            # 🔄 DRY-RUN MODE: Just show what would be done
            if args.dry_run:
                file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
                print(f"\n[DRY-RUN] {idx} - {title}")
                print(f"   📁 Source: {filename}")
                print(f"   📏 Size: {file_size_mb:.2f}MB")
                print(f"   {'🎞️ Would add intro' if args.intro else '⚡ No intro (stream copy)'}")
                continue
            
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
                    desc = extra.get('description', '')
                    
                    # --- ROBUST COMMENT STRIPPING (Telegram Output Only) ---
                    desc = re.split(r'(?i)Comments\s*\n\s*\d+', desc)[0]
                    desc = re.split(r'(?i)Post Comment', desc)[0]
                    desc = re.split(r'(?i)\n\d+\s+Comments', desc)[0]
                    desc = re.split(r'(?m)^\d+ (minutes|hours|days|weeks|months) ago', desc)[0]
                    desc = re.split(r'(?m)^REPLY\s*\n', desc)[0]
                    desc = desc.strip()
                    
                    # Process Links: Inline first
                    remaining_links = []
                    if extra.get('links'):
                        for link in extra['links']:
                            url = link['url']
                            orig_text = link['text']
                            
                            # Clean anchor text for matching
                            match_text = re.sub(r'(?i):\s*CLICK\s*HERE', '', orig_text)
                            match_text = re.sub(r'(?i)CLICK\s*HERE', '', match_text).strip(": ")
                            
                            if not match_text: match_text = "Link"
                            
                            # Pattern to find the anchor text followed by optional colon or space
                            # We search for it in the description to replace it
                            if match_text.lower() in desc.lower():
                                # Case-insensitive replacement while keeping original casing if possible
                                pattern = re.compile(re.escape(match_text), re.IGNORECASE)
                                if pattern.search(desc):
                                    desc = pattern.sub(f"[{match_text}]({url})", desc)
                                    continue # Successfully inlined, don't add to header
                            
                            remaining_links.append(link)
                    
                    # 🔗 LINKS Header (Only for those not inlined)
                    if remaining_links:
                        caption += "🔗 **Links:**\n"
                        for link in remaining_links:
                            link_text = link['text']
                            link_text = re.sub(r'(?i):\s*CLICK\s*HERE', '', link_text)
                            link_text = re.sub(r'(?i)CLICK\s*HERE', '', link_text)
                            link_text = link_text.strip(": ")
                            if not link_text: link_text = "Link"
                            caption += f"• [{link_text}]({link['url']})\n"
                        caption += "\n"
                    
                    # 📝 INFO (The updated description with inline links)
                    if desc:
                        # Clean labels, spacing
                        desc = re.sub(r'(?i)CLICK\s*HERE\s*:?\s*', '', desc)
                        desc = unfragment_text(desc)
                        desc = re.sub(r'\n{3,}', '\n\n', desc).strip()
                        
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
            print(f"[{i}/{total_files}] Processing: {title}")
            print(f"📄 Generated Caption Preview:\n{caption[:200]}...")
            if meta:
                print(f"   ℹ️ Metadata: {meta['course']} | {meta['section']}")
            print(f"{'='*60}")
            
            if not os.path.exists(input_path):
                print(f"❌ Input file not found")
                failed_count += 1
                continue
            
            # Check if already processed
            processed_files = []
            
            output_path = os.path.join(output_dir, filename)
            
            processing_needed = True
            if os.path.exists(output_path):
                if is_video_valid(output_path):
                    print(f"✅ Pre-processed file exists and is valid: {output_path}")
                    processing_needed = False
                    processed_files = [output_path]
                else:
                    print(f"⚠️ Pre-processed file is invalid/corrupted. Re-processing: {output_path}")
                    try: os.remove(output_path)
                    except: pass
                # Decide upload method for existing file
                if not processing_needed:
                    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    upload_method = decide_upload_method(file_size_mb)
                    if upload_method == 'bot' and not bot_available:
                        upload_method = 'user'
                    print(f"🎯 Selected method (Existing): {'Bot' if upload_method == 'bot' else 'User Account'}")

            if processing_needed:
                print(f"🔄 Processing and Compressing to 720p...")
                
                # Step 1: Always process & compress first
                success = await process_video_for_user(input_path, output_path, title, add_intro=args.intro, target_res=args.res)
                
                if success and os.path.exists(output_path):
                    # Step 2: Check size of the COMPRESSED file
                    compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    print(f"📉 Compressed Size: {compressed_size_mb:.2f}MB")
                    
                    upload_method = 'user' # Default for large files
                    
                    # Decide if we need to split based on COMPRESSED size
                    if compressed_size_mb > USER_MAX_SIZE_MB:
                        print(f"⚠️ Still larger than {USER_MAX_SIZE_MB}MB after compression. Splitting...")
                        processed_files = await split_video_for_user(output_path, output_dir, title, target_size_mb=USER_MAX_SIZE_MB, add_intro=False, target_res=args.res)
                    else:
                        # Fits in one part
                        processed_files = [output_path]
                        upload_method = decide_upload_method(compressed_size_mb)
                        if upload_method == 'bot' and not bot_available:
                            upload_method = 'user'
                    
                    print(f"🎯 Selected method (New): {'Bot' if upload_method == 'bot' else 'User Account'}")
                else:
                    print("❌ Processing failed.")
                    failed_count += 1
                    continue
            
            if not processed_files:
                print(f"❌ Error in file processing")
                failed_count += 1
                continue
                
            # Upload Logic
            thumb_path = os.path.join(output_dir, f"thumb_{idx}.jpg")
            has_thumb = False
            
            if processed_files:
                # Try multiple timestamps
                print(f"🖼️ Extracting thumbnail from {os.path.basename(processed_files[0])}...")
                has_thumb = extract_thumbnail(processed_files[0], thumb_path)
                
                if not has_thumb:
                    print(f"❌ CRITICAL Error: Mandatory thumbnail extraction failed for {idx}.")
                    print(f"   Skipping this video to maintain professional quality.")
                    failed_count += 1
                    continue

            if upload_method == "user":
                 # User usually has 1 file
                 for f_path in processed_files:
                     msg = await upload_with_user_account(app, f_path, caption, channel_username, thumb=thumb_path if has_thumb else None)
                     if msg:
                         processed_count += 1
                         print(f"🎉 User account upload successful!")
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
                         print(f"🎉 Bot upload successful!")
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
            # Delay between videos
            if i < total_files:
                delay = 120 if upload_method == "user" else 30  # Longer delay for User Account
                print(f"⏳ Waiting {delay} seconds...")
        
        print(f"\n{'='*60}")
        print(f"📊 Summary:")
        print(f"   📁 Total: {total_files}")
        print(f"   ✅ Successful: {processed_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📈 Success Rate: {(processed_count/total_files)*100:.1f}%")
        print(f"{'='*60}")
        
        # Trigger Indexing
        print("\n🧾 Triggering automatic Index Post update...")
        try:
            cmd = [sys.executable, "scripts/update_captions.py", "--run-now", "--only-index"]
            if args.index_offset > 0:
                cmd.extend(["--index-offset", str(args.index_offset)])
            if args.force_user:
                cmd.append("--force-user")
            subprocess.run(cmd)
            print("✅ Indexing process finished.")
        except Exception as e:
            print(f"⚠️ Failed to trigger indexing: {e}")
        
    except KeyboardInterrupt:
        print("\n⚠️ Stopped by Ctrl+C")
    except Exception as e:
        if "database disk image is malformed" in str(e).lower():
            print(f"\n❌ CRITICAL ERROR: Telegram session database is corrupted.")
            print(f"👉 Fix: Run 'rm scripts/hybrid_account.session' and try again.")
        else:
            print(f"❌ Unexpected Error: {str(e)}")
    finally:
        try:
            if 'app' in locals() and app.is_connected:
                await app.stop()
                print("🔒 Connection closed")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())