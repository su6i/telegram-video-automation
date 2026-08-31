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

# Load environment variables from .env
load_dotenv()

# Bot Config
telegram_token = os.getenv("TELEGRAM_TOKEN")
channel_id = os.getenv("CHANNEL_ID")

# Pyrogram Config
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
channel_username = os.getenv("CHANNEL_USERNAME")

# Additional Config
processed_dir = "processed"
json_log_file = "upload_log.json"

# Environment Validation
required_vars = [telegram_token, channel_id, api_id, api_hash, channel_username]
if not all(required_vars):
    raise ValueError("""
Please set the following variables in .env:
- TELEGRAM_TOKEN (for Bot)
- CHANNEL_ID (for Bot)  
- API_ID (for User Account)
- API_HASH (for User Account)
- CHANNEL_USERNAME (for User Account - e.g. @mychannel)
""")

# Create output directory
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def get_channel_videos(app):
    """Retrieve list of existing videos in the channel"""
    try:
        print("📋 Fetching channel video list...")
        
        uploaded_videos = set()
        message_count = 0
        
        # Get channel messages (last 1000 messages)
        async for message in app.get_chat_history(channel_username, limit=1000):
            message_count += 1
            
            if message.video and message.caption:
                # Caption normalization
                normalized_caption = normalize_title(message.caption)
                uploaded_videos.add(normalized_caption)
                
                # Check parts (for split videos)
                if " - Part " in message.caption:
                    base_title = message.caption.split(" - Part ")[0]
                    normalized_base = normalize_title(base_title)
                    uploaded_videos.add(normalized_base)
            
            # Progress reporting
            if message_count % 100 == 0:
                print(f"   📊 Checked: {message_count} messages")
        
        print(f"✅ Videos found in channel: {len(uploaded_videos)}")
        print(f"📊 Total messages checked: {message_count}")
        
        return uploaded_videos
        
    except Exception as e:
        print(f"❌ Error fetching channel list: {str(e)}")
        return set()

def get_local_videos():
    """Retrieve local video list"""
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
        
        print(f"📁 Local files found: {len(video_files)}")
        return video_files
        
    except Exception as e:
        print(f"❌ Error reading local files: {str(e)}")
        return []

def find_missing_videos(local_videos, uploaded_videos):
    """Find videos that are not yet uploaded"""
    missing_videos = []
    
    for video in local_videos:
        if video['normalized_title'] not in uploaded_videos:
            missing_videos.append(video)
            
    print(f"🔍 Missing videos: {len(missing_videos)}")
    
    if missing_videos:
        print("\n📝 List of missing videos:")
        for i, video in enumerate(missing_videos, 1):
            print(f"   {i:2d}. {video['title']} ({video['size_mb']:.1f}MB)")
    
    return missing_videos


async def retry_failed_uploads():
    """Retry uploading failed/missing files"""
    processed_count = 0
    failed_count = 0
    
    # Create Pyrogram client
    app = Client("hybrid_account", api_id=api_id, api_hash=api_hash)
    
    try:
        await app.start()
        print("🔐 Successfully logged in with user account")
        
        # Test Bot Connection
        bot = Bot(token=telegram_token)
        bot_info = await bot.get_me()
        print(f"🤖 Bot Ready: @{bot_info.username}")
        
        # Phase 1: Get channel video list
        uploaded_videos = await get_channel_videos(app)
        
        # Phase 2: Get local video list
        local_videos = get_local_videos()
        
        # Phase 3: Find missing videos
        missing_videos = find_missing_videos(local_videos, uploaded_videos)
        
        if not missing_videos:
            print("🎉 All files are already uploaded!")
            return
        
        print(f"\n🔄 Starting retry for {len(missing_videos)} files...")
        
        # Phase 4: Upload remaining files
        for i, video in enumerate(missing_videos, 1):
            title = video['title']
            input_path = video['path']
            file_size_mb = video['size_mb']
            
            print(f"\n{'='*60}")
            print(f"[{i}/{len(missing_videos)}] Retrying: {title}")
            print(f"{'='*60}")
            
            upload_method = decide_upload_method(file_size_mb)
            
            print(f"📊 File Size: {file_size_mb:.2f}MB")
            print(f"🎯 Selected method: {'Bot' if upload_method == 'bot' else 'User Account'}")
            
            if upload_method == "bot":
                # Using Bot
                if file_size_mb <= SIZE_THRESHOLD_MB:
                    # Small file - direct processing
                    output_path = os.path.join(output_dir, f"bot_{video['filename']}")
                    success = await process_video_for_bot_safe(input_path, output_path, title)
                    
                    if success:
                        upload_success = await upload_with_bot(output_path, title, telegram_token, channel_id)
                        if upload_success:
                            processed_count += 1
                            print(f"🎉 Bot upload successful!")
                        else:
                            failed_count += 1
                        
                        # Cleanup temporary file
                        try:
                            os.remove(output_path)
                        except:
                            pass
                    else:
                        failed_count += 1
                else:
                    # Large file - split for bot
                    output_files = await split_video_for_bot_safe(input_path, output_dir, title)
                    
                    if output_files:
                        upload_success_count = 0
                        for j, output_file in enumerate(output_files):
                            part_title = f"{title} - Part {j+1}/{len(output_files)}"
                            
                            if await upload_with_bot(output_file, part_title, telegram_token, channel_id):
                                upload_success_count += 1
                            
                            try:
                                os.remove(output_file)
                            except:
                                pass
                            
                            if j < len(output_files) - 1:
                                await asyncio.sleep(5)  # Brief delay between parts
                        
                        if upload_success_count == len(output_files):
                            processed_count += 1
                            print(f"🎊 All parts uploaded with bot!")
                        else:
                            failed_count += 1
                    else:
                        failed_count += 1
            
            else:
                # Using User Account
                output_path = os.path.join(output_dir, f"user_{video['filename']}")
                success = await process_video_for_user_safe(input_path, output_path, title)
                
                if success:
                    upload_success = await upload_with_user_account(app, output_path, title, channel_username)
                    if upload_success:
                        processed_count += 1
                        print(f"🎉 User account upload successful!")
                    else:
                        failed_count += 1
                    
                    # Cleanup temporary file
                    try:
                        os.remove(output_path)
                    except:
                        pass
                else:
                    failed_count += 1
            
            # Delay between videos
            if i < len(missing_videos):
                delay = 120 if upload_method == "user" else 30
                print(f"⏳ Waiting {delay} seconds...")
                await asyncio.sleep(delay)
        
        print(f"\n{'='*60}")
        print(f"📊 Retry Summary:")
        print(f"   📁 Missing files: {len(missing_videos)}")
        print(f"   ✅ Successful: {processed_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📈 Success Rate: {(processed_count/len(missing_videos))*100:.1f}%")
        print(f"{'='*60}")
        
        # Show remaining files
        if failed_count > 0:
            print(f"\n⚠️ Files that are still missing may require manual review.")
        
    except KeyboardInterrupt:
        print("\n⚠️ Stopped by Ctrl+C")
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
    finally:
        await app.stop()
        print("🔒 Connection closed")

if __name__ == "__main__":
    print("🔄 Starting retry for missing files...")
    asyncio.run(retry_failed_uploads())