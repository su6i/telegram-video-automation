import os
import asyncio
from telegram import Bot
from telegram.error import TelegramError
from pyrogram import Client

# Thresholds
SIZE_THRESHOLD_MB = 45
BOT_MAX_SIZE_MB = 45

async def upload_with_bot(video_path, caption, token, channel_id, max_retries=3):
    """Upload video using Telegram Bot API."""
    bot = Bot(token=token)
    
    for attempt in range(max_retries):
        try:
            file_size = os.path.getsize(video_path)
            
            if file_size > BOT_MAX_SIZE_MB * 1024 * 1024:
                print(f"   ❌ File larger than {BOT_MAX_SIZE_MB}MB")
                return False
            
            print(f"   📤 Uploading with bot: {caption} ({file_size/(1024*1024):.1f}MB)")
            
            with open(video_path, "rb") as video_file:
                await bot.send_video(
                    chat_id=channel_id,
                    video=video_file,
                    caption=caption[:1024],
                    supports_streaming=True,
                    read_timeout=180,
                    write_timeout=180
                )
            
            print(f"   ✅ Bot upload successful")
            return True
            
        except TelegramError as e:
            print(f"   ❌ Bot upload error (effort {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(15 * (attempt + 1))
        except Exception as e:
            print(f"   ❌ Unexpected error: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(15 * (attempt + 1))
    
    return False

async def upload_with_user_account(app, video_path, caption, channel_username):
    """Upload video using User Account (Pyrogram)."""
    try:
        from .video_utils import get_video_info  # Circular import avoidance
        
        file_size = os.path.getsize(video_path)
        file_size_gb = file_size / (1024 * 1024 * 1024)
        
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            print(f"   ❌ File larger than 2GB: {file_size_gb:.2f}GB")
            return False
        
        print(f"   📤 Uploading with user account: {caption} ({file_size_gb:.3f}GB)")
        
        video_info = get_video_info(video_path)
        
        message = await app.send_video(
            chat_id=channel_username,
            video=video_path,
            caption=caption,
            duration=int(video_info['duration']) if video_info else 0,
            width=video_info['width'] if video_info else 0,
            height=video_info['height'] if video_info else 0,
            supports_streaming=True,
            progress=lambda current, total: print(f"   📊 {(current/total)*100:.1f}%", end='\r') if int((current/total)*100) % 20 == 0 else None
        )
        
        print(f"\n   ✅ User account upload successful - ID: {message.id}")
        return True
        
    except Exception as e:
        print(f"   ❌ User account upload error: {str(e)}")
        return False

def decide_upload_method(file_size_mb):
    """Decide upload method based on file size."""
    if file_size_mb <= SIZE_THRESHOLD_MB:
        return "bot"  # Bot for small files
    else:
        return "user"  # User account for large files
