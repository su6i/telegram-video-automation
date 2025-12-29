
import os
import sys
import asyncio
import argparse
from pyrogram import Client, enums
from pyrogram.types import InputMediaVideo
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.media_resolver import find_video_file, list_all_videos
from src.video_utils import process_video_for_user_safe as process_video_for_user, get_smart_title

# -- Helper Functions (Copied from process_and_upload to avoid import side-effects) --
STORAGE_DIR = ".storage"
MANIFEST_FILE = os.path.join(STORAGE_DIR, "downloaded_video.txt")
CONTENT_FILE = os.path.join(STORAGE_DIR, "scraped_content.json")

def load_video_metadata(video_filename):
    """
    Parses manifest to find metadata for the given video filename.
    Returns: (Course Title, Section Title, Index, Total Videos) or None
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
                        if "limit" in count_part:
                             course_video_count = count_part.split(" of ")[-1]
                        else:
                             course_video_count = count_part
                    except:
                        course_video_count = "?"
                else:
                    current_course = content
                current_section = "General"
                
            elif line.startswith("## --- "):
                current_section = line.replace("## --- ", "").replace(" ---", "").strip()
                
            elif " | " in line:
                clean_line = line.replace("# [DONE] ", "")
                if clean_line.startswith(f"{file_index} |"):
                    parts = clean_line.split(" | ")
                    url = parts[2].strip() if len(parts) > 2 else ""
                    return {
                        "course": current_course,
                        "section": current_section,
                        "index": file_index,
                        "total": course_video_count,
                        "line_title": parts[1],
                        "url": url
                    }
    except Exception as e:
        print(f"⚠️ Error parsing manifest: {e}")
        
    return None

def load_extra_content(url):
    """Loads description and links from json."""
    if not os.path.exists(CONTENT_FILE):
        return None
    try:
        with open(CONTENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(url)
    except:
        return None
# -------------------------------------------------------------------

# Load Env
load_dotenv()
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

async def main():
    parser = argparse.ArgumentParser(description="Replace a video in Telegram channel while keeping its position.")
    parser.add_argument("filename", help="Partial filename to search for (e.g. '002' or 'Join')")
    parser.add_argument("message_id", type=int, help="The Message ID in Telegram to edit")
    
    args = parser.parse_args()
    
    # 1. Init Client
    print(f"🔌 Connecting to Telegram session in 'scripts/'...")
    app = Client("hybrid_account", api_id=API_ID, api_hash=API_HASH, workdir="scripts")
    await app.start()
    
    # 2. Find File
    target_file = None
    all_videos = list_all_videos()
    for fname, fpath in all_videos:
        if args.filename.lower() in fname.lower():
            target_file = fpath
            print(f"✅ Found file: {fname}")
            break
            
    if not target_file:
        print(f"❌ File containing '{args.filename}' not found.")
        return

    # 3. Process Video (Faststart)
    print("⚙️  Processing video (preparing for streaming)...")
    # We use a temp path
    output_dir = os.getenv("PROCESSED_DIR", "processed")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    temp_output = os.path.join(output_dir, f"REPLACE_{os.path.basename(target_file)}")
    
    # We reuse shared logic if possible, or simple ffmpeg call
    # Let's use the robust one from video_utils if importable, or just direct ffmpeg here for simplicity
    # actually we imported process_video_for_user
    
    success = await process_video_for_user(target_file, temp_output, "Replacement", add_intro=False)
    
    if not success:
        print("❌ Processing failed.")
        return

    # 4. Generate Caption (Fresh)
    print("📝 Generating fresh caption...")
    # Logic copied from process_and_upload to ensure consistency
    file_basename = os.path.basename(target_file)
    title = get_smart_title(target_file)
    meta = load_video_metadata(file_basename)
    caption = title
    
    if meta:
        if meta['total'] > 0:
            caption = f"**{meta['course']} ({meta['total']} videos)**\n"
        else:
            caption = f"**{meta['course']}**\n"

        if meta['section'] and meta['section'] != "General":
            caption += f"{meta['section']}\n"
        
        final_title = meta['line_title'] if meta['line_title'] else title
        caption += f"{meta['index']} - {final_title}\n"
        
        extra = load_extra_content(meta['url'])
        if extra:
            if extra.get('links'):
                caption += "\n🔗 Links:\n"
                for link in extra['links']:
                    caption += f"• [{link['text']}]({link['url']})\n"
            
            if extra.get('description'):
                desc = extra['description']
                print(f"\n🔍 [Debug] Raw Description Found. Length: {len(desc)} chars")
                print(f"📄 Preview: {desc[:200].replace(chr(10), ' ')}...")
                
                # Remove comments (Robust Regex)
                # Patterns: 
                # 1. "Comments\n123" (Kajabi standard)
                # 2. "Post Comment" (Input field label)
                # 3. "Comments\r\n"
                # Capture everything BEFORE the first occurrence of these
                # Look for "Comments" followed implicitly by digits or newlines, or "Post Comment"
                # We use a non-greedy match for the content, stopping at the comment block
                
                # Pattern 1: Explicit "Comments" header with a number on next line
                desc = re.split(r'(?i)Comments\s*\n\s*\d+', desc)[0]
                
                # Pattern 2: "Post Comment" button/label
                desc = re.split(r'(?i)Post Comment', desc)[0]
                
                # Pattern 3: "X Comments" at the end (rare but possible)
                desc = re.split(r'(?i)\n\d+\s+Comments', desc)[0]
                
                desc = desc.strip()
                # Format Headers (e.g. "12/25 Update!..." -> "**12/25 Update!...**")
                import re
                # Bold lines that start with a date pattern or "Update" and are short
                # Add '\n' to replacement to ensure empty line before header
                desc = re.sub(r'(^|\n)(\d{1,2}/\d{1,2} Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
                desc = re.sub(r'(^|\n)(Update!.*?)(?=\n|$)', r'\1\n**\2**', desc)
                
                desc = desc.strip()
                # Fix potential triple newlines
                desc = desc.replace("\n\n\n", "\n\n")
                
                full_desc = "" # We won't use full_desc anymore, we use overflow_text
                overflow_text = ""
                need_overflow = False
                
                if desc:
                    # Calculate remaining space (Telegram limit 1024)
                    current_len = len(caption) + len("\n\n📝 Info:\n")
                    remaining = 1024 - current_len
                    
                    if len(desc) <= remaining:
                        # Fits completely
                        caption += f"\n\n📝 Info:\n{desc}"
                    else:
                        # Needs splitting
                        # Try to find a clean break point within 'remaining' limit
                        candidate = desc[:remaining]
                        
                        # Priority 1: Double Newline (Paragraph)
                        last_break = candidate.rfind('\n\n')
                        
                        # Priority 2: Single Newline (Line) - Only if paragraph not found
                        if last_break == -1:
                            last_break = candidate.rfind('\n')
                            
                        # Priority 3: Sentence End (. ) - Only if line not found
                        if last_break == -1:
                            last_break = candidate.rfind('. ')
                            
                        # Priority 4: Space - Last resort
                        if last_break == -1:
                            last_break = candidate.rfind(' ')
                            
                        if last_break > 0:
                            # Split cleanly
                            visible_part = desc[:last_break+1].strip() # include the punctuation/newline
                            overflow_part = desc[last_break+1:].strip()
                            
                            caption += f"\n\n📝 Info:\n{visible_part}\n\n⬇️ (See next message)"
                            overflow_text = overflow_part
                            need_overflow = True
                        else:
                            # Fallback if even one word is too big (unlikely) or no spaces
                            caption += f"\n\n📝 Info:\n{candidate}..."
                            overflow_text = desc[remaining:]
                            need_overflow = True

    # 5. Edit Message
    print(f"📤 Replacing media in Message ID {args.message_id}...")
    try:
        # Progress hook
        async def progress(current, total):
            print(f"\r🚀 Uploading: {current * 100 / total:.1f}%", end="")

        await app.edit_message_media(
            chat_id=CHANNEL_ID,
            message_id=args.message_id,
            media=InputMediaVideo(
                media=temp_output,
                caption=caption,
                parse_mode=enums.ParseMode.MARKDOWN
            )
        )
        print("\n✅ Success! Video replaced.")
        
        # 6. Send Overflow Message if needed
        if need_overflow and overflow_text:
            print("📄 Description split. Sending remainder as reply...")
            await app.send_message(
                chat_id=CHANNEL_ID,
                text=f"📄 **Continued:**\n\n{overflow_text}",
                reply_to_message_id=args.message_id,
                disable_web_page_preview=True
            )
            print("✅ Overflow message sent.")
        
    except Exception as e:
        print(f"\n❌ Edit failed: {e}")
    finally:
        # Cleanup
        if os.path.exists(temp_output):
            os.remove(temp_output)
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
