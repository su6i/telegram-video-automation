# update_captions.py
import os
import re
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import RPCError, ChatAdminRequired
from pyrogram.enums import ChatType, ParseMode

# =========================== Env & Config ===========================
load_dotenv()

API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
INVITE_LINK = os.getenv("INVITE_LINK", "")
CHANNEL_ID_ENV = os.getenv("CHANNEL_ID", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
VIDEO_DIR = os.getenv("VIDEO_DIR", "").strip()
RUN_NOW = os.getenv("RUN_NOW", "").lower() in ("1", "true", "yes", "y")
ONLY_INDEX = os.getenv("ONLY_INDEX", "").lower() in ("1", "true", "yes", "y")
# Add this variable to settings
RENAME_FILES = os.getenv("RENAME_FILES", "").lower() in ("1", "true", "yes", "y")

if not API_ID or not API_HASH:
    raise ValueError("Set API_ID and API_HASH in .env file.")

SESSION_NAME = "caption_updater_bot" if BOT_TOKEN else "caption_updater_user"

# RTL/LTR markers
RLM = "\u200F"
LRM = "\u200E"
RTL_MARKS_RE = re.compile(r"[\u200e\u200f]")

# =========================== Title helpers ===========================
def clean_caption(caption: str) -> str:
    if not caption:
        return ""
    cleaned = caption.strip()
    # Remove any old numbering
    patterns = [
        r'^\s*#?\d{1,4}\s*[-\.\:\|]\s*',
        r'^\s*\[\d{1,4}\]\s*',
        r'^\s*\(\d{1,4}\)\s*',
        r'^\s*\d{1,4}\s+',
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def create_numbered_caption(number: int, original_caption: str) -> str:
    title = clean_caption(original_caption or "")
    base = f"{number:03d} - {title}" if title else f"{number:03d}"
    return f"{RLM}{base}"

# =========================== File time helpers ===========================
def get_file_timestamp(p: Path) -> Optional[datetime]:
    try:
        st = p.stat()
        birth = getattr(st, "st_birthtime", None)
        ts = birth if birth else st.st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None

def load_video_files_sorted(video_dir: Optional[str]) -> List[Tuple[Path, datetime]]:
    result: List[Tuple[Path, datetime]] = []
    if not video_dir:
        print("🗂️ VIDEO_DIR not set.")
        return result
    root = Path(video_dir).expanduser().resolve()
    print(f"🗂️ VIDEO_DIR: {root} (for file timestamps)")
    if not root.exists():
        print("⚠️ VIDEO_DIR does not exist.")
        return result
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"):
            dt = get_file_timestamp(p)
            if dt:
                result.append((p, dt))
    result.sort(key=lambda x: x[1])
    return result

# =========================== Pyrogram ===========================
def create_pyrogram_client() -> Client:
    if BOT_TOKEN:
        print("🤖 Bot mode active.")
        return Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
    else:
        print("👤 User mode active.")
        return Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

def is_channel_like(t) -> bool:
    try:
        return t in (ChatType.CHANNEL, ChatType.SUPERGROUP)
    except Exception:
        return str(t).lower() in ("chattype.channel", "chattype.supergroup", "channel", "supergroup")

async def resolve_channel(app: Client) -> Tuple[Optional[int], Optional[str]]:
    # 1) INVITE_LINK
    if INVITE_LINK:
        try:
            await app.join_chat(INVITE_LINK)
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                print("ℹ️ You are already a member of the channel.")
            else:
                print(f"⚠️ join_chat: {e}")
        try:
            chat = await app.get_chat(INVITE_LINK)
            if is_channel_like(chat.type):
                print(f"✅ Target from INVITE_LINK: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ INVITE_LINK points to {chat.type}.")
        except Exception as e:
            print(f"⚠️ get_chat(INVITE_LINK): {e}")

    # 2) CHANNEL_ID
    if CHANNEL_ID_ENV:
        try:
            cid = int(CHANNEL_ID_ENV)
            chat = await app.get_chat(cid)
            if is_channel_like(chat.type):
                print(f"✅ Target from CHANNEL_ID: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ CHANNEL_ID points to {chat.type}.")
        except Exception as e:
            print(f"⚠️ CHANNEL_ID invalid or no access: {e}")

    # 3) CHANNEL_USERNAME
    if CHANNEL_USERNAME:
        try:
            chat = await app.get_chat(CHANNEL_USERNAME)
            if is_channel_like(chat.type):
                print(f"✅ Target from CHANNEL_USERNAME: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ {CHANNEL_USERNAME} => {chat.type}")
        except Exception as e:
            print(f"⚠️ CHANNEL_USERNAME invalid or no access: {e}")

    # 4) fallback
    print("🔍 Searching dialogs for channel containing videos...")
    try:
        best = None
        async for d in app.get_dialogs():
            if not is_channel_like(d.chat.type):
                continue
            cnt = 0
            async for m in app.get_chat_history(d.chat.id, limit=200):
                if m.video:
                    cnt += 1
            if cnt > 0 and (not best or cnt > best[0]):
                best = (cnt, d.chat.id, d.chat.title)
        if best:
            print(f"✅ Selected: {best[2]} (ID: {best[1]}) Videos: {best[0]}")
            return best[1], best[2]
    except Exception as e:
        print(f"⚠️ Error in get_dialogs(): {e}")

    return None, None

# =========================== Fetch & Plan ===========================
async def get_all_videos_info(app: Client, chat_id: int):
    videos = []
    checked = 0
    print("📥 Reading channel history...")
    async for m in app.get_chat_history(chat_id, limit=0):
        checked += 1
        if m.video:
            videos.append({
                "message_id": m.id,
                "caption": m.caption or "",
                "date": m.date if (m.date and m.date.tzinfo) else (m.date.replace(tzinfo=timezone.utc) if m.date else None),
            })
    print(f"✅ Total messages checked: {checked} | Videos: {len(videos)}")
    return videos

async def save_backup(videos, filename="backup_captions.json"):
    try:
        payload = [{
            "message_id": v["message_id"],
            "caption": v["caption"],
            "date": v["date"].astimezone(timezone.utc).isoformat() if isinstance(v["date"], datetime) else None
        } for v in videos]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"💾 Backup saved: {filename}")
    except Exception as e:
        print(f"⚠️ Error saving backup: {e}")

def plan_numbering_by_files(videos, files_sorted: List[Tuple[Path, datetime]]):
    if files_sorted and len(files_sorted) == len(videos):
        videos_sorted_by_msg_date = sorted(videos, key=lambda x: x["date"] or datetime(1970,1,1,tzinfo=timezone.utc))
        planned = []
        for i, v in enumerate(videos_sorted_by_msg_date, start=1):
            planned.append({
                "message_id": v["message_id"],
                "old_caption": v["caption"],
                "new_caption": create_numbered_caption(i, v["caption"]),
                "sort_date": files_sorted[i-1][1]
            })
        print(f"🗂️ Video files identified: {len(files_sorted)}")
        return planned
    else:
        planned = []
        videos_sorted = sorted(videos, key=lambda x: x["date"] or datetime(1970,1,1,tzinfo=timezone.utc))
        for i, v in enumerate(videos_sorted, start=1):
            planned.append({
                "message_id": v["message_id"],
                "old_caption": v["caption"],
                "new_caption": create_numbered_caption(i, v["caption"]),
                "sort_date": v["date"]
            })
        if not files_sorted:
            print("🛈 File timestamps not available; sorted by message date.")
        else:
            print(f"🛈 File count does not match video count ({len(files_sorted)} != {len(videos)}). Using message date.")
        return planned

# =========================== Apply updates ===========================
async def apply_updates(app: Client, chat_id: int, planned, dry_run=True):
    ok, fail = 0, 0
    print(f"\n{'🔄 Dry run (No changes)' if dry_run else '📝 Applying updates'} | Count: {len(planned)}")
    for i, item in enumerate(planned, start=1):
        mid = item["message_id"]
        oldc = item["old_caption"]
        newc = item["new_caption"]
        sdt = item.get("sort_date")
        print(f"\n[{i}/{len(planned)}] msg_id={mid}")
        if sdt:
            print(f"  🗓️ sort_date: {sdt.isoformat() if isinstance(sdt, datetime) else sdt}")
        print(f"  📝 Old: {oldc}")
        print(f"  🆕 New: {newc}")
        if dry_run:
            ok += 1
            continue
        try:
            await app.edit_message_caption(chat_id, mid, newc, parse_mode=ParseMode.HTML)
            ok += 1
            await asyncio.sleep(0.7)
        except ChatAdminRequired:
            print("  ❌ Admin privileges required to edit messages in this channel.")
            fail += 1
        except RPCError as e:
            print(f"  ❌ Error: {e}")
            fail += 1
            if "FLOOD" in str(e).upper():
                print("  ⏳ Pausing for 30 seconds...")
                await asyncio.sleep(30)
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            fail += 1
    print(f"\n📊 Result: Successful {ok} | Failed {fail}")
    return ok, fail

# =========================== Index posts ===========================
def tg_private_link(chat_id: int, message_id: int) -> str:
    internal = abs(chat_id) - 1000000000000
    return f"https://t.me/c/{internal}/{message_id}"

def safe_extract_number(new_caption: str) -> int:
    """Extracts number from start of caption; RLM/LRM are removed."""
    if not new_caption:
        return 0
    s = RTL_MARKS_RE.sub("", new_caption)
    m = re.match(r"^\s*(\d{1,4})", s)
    return int(m.group(1)) if m else 0

async def create_index_posts(app: Client, chat_id: int, planned, title="📚 Video Index", per_post_limit=4090):
    # Sort reliably
    planned_sorted = sorted(planned, key=lambda x: safe_extract_number(x.get("new_caption", "")))

    header = f"{RLM}<b>{title}</b>\n"
    chunk_lines: List[str] = []
    chunk_len = len(header)
    first_index_msg_id: Optional[int] = None

    def format_line(item):
        newc = RTL_MARKS_RE.sub("", item["new_caption"])
        m = re.match(r'^\s*(\d{3})\s*-\s*(.*)$', newc)
        num = m.group(1) if m else "???"
        title_txt = m.group(2) if m else newc
        mid = item["message_id"]
        href = tg_private_link(chat_id, mid)
        safe_title = (title_txt
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))
        return f'{RLM}{num} - <a href="{href}">{safe_title}</a>'

    async def flush():
        nonlocal chunk_lines, chunk_len, first_index_msg_id
        if not chunk_lines:
            return
        chunk = header + "\n".join(chunk_lines)
        msg = await app.send_message(
            chat_id,
            chunk,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        if first_index_msg_id is None:
            try:
                await msg.pin(disable_notification=True)
                print("📌 Index post pinned.")
            except Exception:
                pass
            first_index_msg_id = msg.id
        # reset
        chunk_lines = []
        chunk_len = len(header)

    # Build body
    for item in planned_sorted:
        line = format_line(item)
        projected = chunk_len + (1 if chunk_lines else 0) + len(line)
        if projected > per_post_limit:
            await flush()
        if chunk_lines:
            chunk_lines.append(line)
            chunk_len += 1 + len(line)
        else:
            chunk_lines.append(line)
            chunk_len += len(line)

    # Final Buffer
    await flush()
    print("✅ Index post sent.")

def plan_from_existing(videos):
    # Uses existing numbers in captions; no changes made to captions.
    def extract_num(caption: str) -> int:
        s = RTL_MARKS_RE.sub("", caption or "")
        # Try various numbering patterns
        patterns = [
            r'^\s*#?\s*0*(\d{1,4})\s*[-\.\:\|]',  # 016 - Title
            r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',      # 016 Title
            r'^\s*#?\s*0*(\d{1,4})\s*$',          # 016 Only
            r'^\s*\[\s*0*(\d{1,4})\s*\]',         # [016]
            r'^\s*\(\s*0*(\d{1,4})\s*\)',         # (016)
        ]
        for pattern in patterns:
            m = re.match(pattern, s)
            if m:
                return int(m.group(1))
        return 999999  # If no number found, put at end of list

    # Sort based on extracted number only
    vids_sorted = sorted(videos, key=lambda v: extract_num(v.get("caption", "")))

    planned = []
    for v in vids_sorted:
        planned.append({
            "message_id": v["message_id"],
            "old_caption": v["caption"] or "",
            "new_caption": v["caption"] or "",   # No change
            "sort_date": v.get("date")
        })
    
    print(f"📋 Videos sorted by caption number:")
    for i, item in enumerate(planned[:5]):  # Show first 5 for verification
        num = extract_num(item["old_caption"])
        print(f"  {i+1}. Number: {num} | Caption: {item['old_caption'][:50]}...")
    
    return planned


# Add this function to main code

def extract_number_from_caption(caption: str) -> int:
    """Extract number from caption using various patterns"""
    if not caption:
        return 999999
    
    s = RTL_MARKS_RE.sub("", caption)
    patterns = [
        r'^\s*#?\s*0*(\d{1,4})\s*[-\.\:\|]',  # 016 - Title
        r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',      # 016 Title  
        r'^\s*#?\s*0*(\d{1,4})\s*$',          # 016 Only
        r'^\s*\[\s*0*(\d{1,4})\s*\]',         # [016]
        r'^\s*\(\s*0*(\d{1,4})\s*\)',         # (016)
    ]
    
    for pattern in patterns:
        m = re.match(pattern, s)
        if m:
            return int(m.group(1))
    return 999999

def clean_filename(text: str) -> str:
    """Clean text for use in filename"""
    if not text:
        return ""
    # Remove illegal characters for filenames
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    # Remove extra spaces
    text = re.sub(r'\s+', ' ', text).strip()
    # Limit length
    return text[:100] if len(text) > 100 else text

async def rename_video_files_by_captions(videos, video_dir: str, dry_run=True):
    """Rename video files based on caption numbering"""
    if not video_dir:
        print("⚠️ VIDEO_DIR not set.")
        return
    
    root = Path(video_dir).expanduser().resolve()
    if not root.exists():
        print(f"⚠️ Directory {root} does not exist.")
        return
    
    # Find video files
    video_files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"):
            video_files.append(p)
    
    print(f"🎬 Video files found: {len(video_files)}")
    print(f"📺 Channel videos: {len(videos)}")
    
    if len(video_files) != len(videos):
        print("⚠️ Video file count does not match channel video count!")
        response = input("Do you want to continue? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            return
    
    # Sort channel videos by caption number
    videos_sorted = sorted(videos, key=lambda v: extract_number_from_caption(v.get("caption", "")))
    
    # Sort files by creation date
    files_with_dates = []
    for p in video_files:
        dt = get_file_timestamp(p)
        if dt:
            files_with_dates.append((p, dt))
    
    files_sorted = sorted(files_with_dates, key=lambda x: x[1])
    
    print(f"\n{'🔄 Dry run (No renaming)' if dry_run else '📝 Real renaming'}")
    print("-" * 80)
    
    renamed_count = 0
    for i, (video_info, (file_path, _)) in enumerate(zip(videos_sorted, files_sorted)):
        caption = video_info.get("caption", "")
        number = extract_number_from_caption(caption)
        
        # Extract title from caption
        clean_cap = clean_caption(caption)
        title = clean_filename(clean_cap) if clean_cap else "untitled"
        
        # Construct new name
        old_name = file_path.name
        extension = file_path.suffix
        new_name = f"{number:03d} - {title}{extension}"
        new_path = file_path.parent / new_name
        
        print(f"\n[{i+1}/{len(files_sorted)}]")
        print(f"  📄 Old: {old_name}")
        print(f"  🆕 New: {new_name}")
        print(f"  📝 Caption: {caption[:60]}{'...' if len(caption) > 60 else ''}")
        
        # Check for duplicates
        if new_path.exists() and new_path != file_path:
            print(f"  ⚠️ File with new name already exists!")
            continue
        
        if not dry_run:
            try:
                file_path.rename(new_path)
                print(f"  ✅ Rename successful")
                renamed_count += 1
            except Exception as e:
                print(f"  ❌ Rename error: {e}")
        else:
            renamed_count += 1
    
    print(f"\n📊 Result: {renamed_count} files {'renameable' if dry_run else 'renamed'}")
    
    if dry_run:
        print("\n⚠️ To apply real changes, add RENAME_FILES=true to .env.")



# =========================== Main ===========================
async def main():
    files_sorted = load_video_files_sorted(VIDEO_DIR)
    if not files_sorted:
        print("🗂️ VIDEO_DIR: (In this version, only message dates may be used)")

    app = create_pyrogram_client()
    await app.start()
    try:
        chat_id, chat_title = await resolve_channel(app)
        if not chat_id:
            print("❌ No channel found or no access. Check .env parameters.")
            return

        print(f"📺 Target Channel: {chat_title} (ID: {chat_id})")

        videos = await get_all_videos_info(app, chat_id)
        await save_backup(videos)

        if ONLY_INDEX:
            print("🛈 ONLY_INDEX is active: No captions will be edited; only index post will be created/updated.")
            planned = plan_from_existing(videos)
        else:
            files_sorted = load_video_files_sorted(VIDEO_DIR)
            planned = plan_numbering_by_files(videos, files_sorted)
            # Test/Apply phase only when ONLY_INDEX is disabled
            await apply_updates(app, chat_id, planned, dry_run=not RUN_NOW)
            if not RUN_NOW:
                print("⚠️ No changes applied. To apply for real, set RUN_NOW=true in .env.")

        print("🧾 Generating Index Post...")
        await create_index_posts(app, chat_id, planned, title="📚 Video List")
        if VIDEO_DIR:
            print("\n🎬 Numbering video files...")
            await rename_video_files_by_captions(videos, VIDEO_DIR, dry_run=not RENAME_FILES)


    finally:
        await app.stop()
        print("🔒 Connection closed.")

if __name__ == "__main__":
    asyncio.run(main())
