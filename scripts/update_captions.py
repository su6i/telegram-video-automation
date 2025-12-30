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
    # Remove LRM/RLM markers first
    cleaned = RTL_MARKS_RE.sub("", caption).strip()
    
    # Remove any old numbering (001, 001 -, 001_, [001], etc)
    patterns = [
        r'^\s*#?\d{1,4}\s*[-\.\:\|_]\s*',
        r'^\s*#?\d{1,4}_',
        r'^\s*#?\d{1,4}-',
        r'^\s*\[\d{1,4}\]\s*',
        r'^\s*\(\d{1,4}\)\s*',
        r'^\s*\d{1,4}\s+',
    ]
    # Apply twice to catch double-numbering if present
    for _ in range(2):
        for p in patterns:
            cleaned = re.sub(p, "", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def load_manifest_hierarchy() -> Dict[str, Dict[str, str]]:
    """Returns {index: {'course': ..., 'section': ...}}"""
    manifest_path = os.path.join(".storage", "downloaded_video.txt")
    if not os.path.exists(manifest_path):
        return {}
    
    hierarchy = {}
    current_course = "Unknown Course"
    current_section = "General"
    
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.startswith("# === "):
                    current_course = line.replace("# === ", "").split(" ===")[0].strip()
                    if "(" in current_course:
                        current_course = current_course.split("(")[0].strip()
                elif line.startswith("## --- "):
                    current_section = line.replace("## --- ", "").replace(" ---", "").strip()
                elif "|" in line:
                    idx_part = line.split("|")[0].strip()
                    if idx_part.startswith("# [DONE] "):
                        idx_part = idx_part.replace("# [DONE] ", "").strip()
                    # Catch index like 001
                    m = re.match(r'^(\d{3})', idx_part)
                    if m:
                         hierarchy[m.group(1)] = {"course": current_course, "section": current_section}
    except:
        pass
    return hierarchy

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
def create_pyrogram_client(force_user=False) -> Client:
    if BOT_TOKEN and not force_user:
        print("🤖 Bot mode active.")
        return Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
    else:
        print("👤 User mode active (hybrid_account).")
        # Use the same session as the uploader for consistency
        return Client("hybrid_account", api_id=API_ID, api_hash=API_HASH)

def is_channel_like(t) -> bool:
    try:
        return t in (ChatType.CHANNEL, ChatType.SUPERGROUP)
    except Exception:
        return str(t).lower() in ("chattype.channel", "chattype.supergroup", "channel", "supergroup")

async def resolve_channel(app: Client) -> Tuple[Optional[int], Optional[str]]:
    # 1) CHANNEL_ID
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

    # 2) INVITE_LINK
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
    print("🔍 Searching your account dialogs for the target channel...")
    try:
        best = None
        async for d in app.get_dialogs():
            if not is_channel_like(d.chat.type):
                continue
            # Basic heuristic: Search for channels with "Course" or related words if multiple exist
            if best is None: # Just pick the first one we find for now if none specified
                best = (0, d.chat.id, d.chat.title)
                
            cnt = 0
            async for m in app.get_chat_history(d.chat.id, limit=50):
                if m.video:
                    cnt += 1
            if cnt > 0 and (not best or cnt > best[0]):
                best = (cnt, d.chat.id, d.chat.title)
        if best:
            print(f"✅ Found potential target: {best[2]} (ID: {best[1]}) with {best[0]} videos.")
            return best[1], best[2]
    except Exception as e:
        print(f"⚠️ Search failed: {e}")

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
        hierarchy = load_manifest_hierarchy()
        for i, v in enumerate(videos_sorted_by_msg_date, start=1):
            file_path = files_sorted[i-1][0]
            idx_str = f"{i:03d}"
            h = hierarchy.get(idx_str, {})
            planned.append({
                "message_id": v["message_id"],
                "old_caption": v["caption"],
                "new_caption": create_numbered_caption(i, v["caption"]),
                "sort_date": files_sorted[i-1][1],
                "display_name": file_path.stem,
                "course": h.get("course"),
                "section": h.get("section")
            })
        print(f"🗂️ Video files identified: {len(files_sorted)}")
        return planned
    else:
        planned = []
        videos_sorted = sorted(videos, key=lambda x: x["date"] or datetime(1970,1,1,tzinfo=timezone.utc))
        hierarchy = load_manifest_hierarchy()
        for i, v in enumerate(videos_sorted, start=1):
            # Try to match a file by number
            matched_file = None
            for p, dt in (files_sorted or []):
                if safe_extract_number(p.name) == i:
                    matched_file = p
                    break
            
            idx_str = f"{i:03d}"
            h = hierarchy.get(idx_str, {})
            planned.append({
                "message_id": v["message_id"],
                "old_caption": v["caption"],
                "new_caption": create_numbered_caption(i, v["caption"]),
                "sort_date": v["date"],
                "display_name": matched_file.stem if matched_file else None,
                "course": h.get("course"),
                "section": h.get("section")
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
        print(f"  🎬 File: {item.get('display_name', 'Unknown')}")
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

def safe_extract_number(text: str) -> int:
    """Extracts number from start of caption/filename; RLM/LRM are ignored."""
    if not text:
        return 999999
    s = RTL_MARKS_RE.sub("", text)
    # Try various numbering patterns (001, [001], #001, etc)
    patterns = [
        r'^\s*#?\s*0*(\d{1,4})\s*[-\.\:\|]',
        r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',
        r'^\s*#?\s*0*(\d{1,4})\s*$',
        r'^\s*\[\s*0*(\d{1,4})\s*\]',
        r'^\s*\(\s*0*(\d{1,4})\s*\)',
    ]
    for pattern in patterns:
        m = re.search(pattern, s)
        if m:
            return int(m.group(1))
    return 999999

async def create_index_posts(app: Client, chat_id: int, planned, title="📚 Video Index", per_post_limit=4090, start_offset=0, dry_run=True):
    # Sort reliably
    planned_sorted = sorted(planned, key=lambda x: safe_extract_number(x.get("new_caption", "")))

    # Detect Course Title from hierarchy if available
    course_title = title
    if planned_sorted and planned_sorted[0].get("course"):
        course_title = f"🎓 {planned_sorted[0]['course']}"

    header = f"{LRM}<b>{course_title}</b>\n"
    chunk_lines: List[str] = []
    chunk_len = len(header)
    
    last_section = None
    
    # We will look for messages to edit if start_offset > 0
    # But usually, it's easier to just fetch the last N messages or specific ones.
    # The user says "From message ID X" essentially. 
    # Let's implementation a simple logic: if start_offset is a large number, it's a Message ID.
    # If it's small, it's an offset from the first message in the channel?
    
    placeholders = []
    if start_offset > 0:
        print(f"📥 Collecting index placeholders starting from Message ID: {start_offset}...")
        try:
            # Safer way: Fetch a range of message IDs
            target_ids = list(range(start_offset, start_offset + 30))
            msgs = await app.get_messages(chat_id, target_ids)
            for m in msgs:
                if m.empty or not m.text: continue
                if not m.video and not m.photo and not m.document:
                    placeholders.append(m.id)
            
            print(f"   📂 Found {len(placeholders)} valid placeholder messages.")
        except Exception as e:
            print(f"⚠️ Error fetching placeholders: {e}")

    placeholder_idx = 0

    def format_line(item):
        display_name = item.get("display_name")
        newc = RTL_MARKS_RE.sub("", item["new_caption"])
        
        # Determine number and title
        m = re.match(r'^\s*(\d{3})', newc)
        num_str = m.group(1) if m else "???"
        
        if display_name:
            # Clean underscores and redundant numbers from filename
            title_txt = clean_caption(display_name).replace("_", " ")
        else:
            # Fallback to caption: only take first line
            first_line = newc.split('\n')[0].strip()
            title_txt = re.sub(r'^\s*(\d{3})\s*[-\.\:\|_]\s*', '', first_line)
        
        # Truncate if too long
        if len(title_txt) > 65:
            title_txt = title_txt[:62] + "..."
            
        mid = item["message_id"]
        href = tg_private_link(chat_id, mid)
        safe_title = (title_txt
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))
        return f'{LRM}{num_str} - <a href="{href}">{safe_title}</a>'

    async def flush():
        nonlocal chunk_lines, chunk_len, placeholder_idx
        if not chunk_lines:
            return True
        chunk = header + "\n".join(chunk_lines)
        
        target_mid = placeholders[placeholder_idx] if placeholder_idx < len(placeholders) else None
        
        if target_mid:
            try:
                # SAFETY CHECK: Collision protection
                msg = await app.get_messages(chat_id, target_mid)
                if msg.video or msg.photo or msg.document:
                    print(f"   🛑 STOPPED: Collision detected at Message #{target_mid}. It contains media.")
                    print("   👉 I will not overwrite your video files. Please provide enough text placeholders.")
                    return False # Signal to stop

                await app.edit_message_text(chat_id, target_mid, chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                print(f"   📝 Updated Index Post #{target_mid} ({placeholder_idx + 1}/{len(placeholders)})")
                placeholder_idx += 1
            except Exception as e:
                print(f"   ⚠️ Edit failed for #{target_mid}, skipping: {e}")
                # Don't return False here, just skip one
        else:
            # No more placeholders, send as new
            if dry_run:
                print(f"   🆕 Would send new Index Post (Dry Run)")
                # Increment index so we don't spam "would send" too much? No, it's fine.
                placeholder_idx += 1 
            else:
                msg = await app.send_message(chat_id, chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                print(f"   🆕 Sent new Index Post #{msg.id}")
                target_mid = msg.id

        if placeholder_idx == 1: # Pin the first one
            try: await app.pin_chat_message(chat_id, target_mid, disable_notification=True)
            except: pass

        # reset
        chunk_lines = []
        chunk_len = len(header)
        return True

    # Build body
    for item in planned_sorted:
        section = item.get("section")
        if section and section != last_section:
            section_header = f"\n{LRM}<b>📁 {section}</b>"
            # If adding section header exceeds limit, flush first
            if chunk_len + len(section_header) > per_post_limit:
                if not await flush(): break
            chunk_lines.append(section_header)
            chunk_len += len(section_header)
            last_section = section

        line = format_line(item)
        projected = chunk_len + (1 if chunk_lines else 0) + len(line)
        if projected > per_post_limit:
            if not await flush():
                break
        if chunk_lines:
            chunk_lines.append(line)
            chunk_len += 1 + len(line)
        else:
            chunk_lines.append(line)
            chunk_len += len(line)

    # Final Buffer
    await flush()

    # OVERFLOW WARNING
    if len(planned_sorted) > 0 and placeholder_idx >= len(placeholders) and placeholders:
        # Check if we still had lines to write
        # (This is a bit simplified, but accurate if flush() was called and no more placeholders exist)
        print("\n" + "!"*60)
        print("⚠️  WARNING: INDEX OVERFLOW DETECTED!")
        print("⚠️  Video count exceeds the number of reserved placeholder messages.")
        print(f"⚠️  Only {placeholder_idx} index posts were updated.")
        print("👉  Fix: Create more blank messages in the channel and run again.")
        print("!"*60 + "\n")

def plan_from_existing(videos, files_sorted: List[Tuple[Path, datetime]] = None):
    # Uses existing numbers in captions; no changes made to captions.
    vids_sorted = sorted(videos, key=lambda v: safe_extract_number(v.get("caption", "")))

    hierarchy = load_manifest_hierarchy()
    for i, v in enumerate(vids_sorted, start=1):
        num = safe_extract_number(v.get("caption", ""))
        
        # Try to match a local file by number if available
        matched_file = None
        if files_sorted:
            for p, dt in files_sorted:
                if safe_extract_number(p.name) == num:
                    matched_file = p
                    break

        idx_str = f"{num:03d}"
        h = hierarchy.get(idx_str, {})
        planned.append({
            "message_id": v["message_id"],
            "old_caption": v["caption"] or "",
            "new_caption": v["caption"] or "",   # No change
            "sort_date": v.get("date"),
            "display_name": matched_file.stem if matched_file else None,
            "course": h.get("course"),
            "section": h.get("section")
        })
    
    print(f"📋 Videos sorted by existing numbering:")
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




# =========================== Main ===========================
async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tool to fix video numbering and update the Table of Contents (Index).")
    parser.add_argument("--run-now", action="store_true", help="Actually apply changes to Telegram (default is dry-run)")
    parser.add_argument("--only-index", action="store_true", help="Only update the Table of Contents, don't change video captions")
    parser.add_argument("--index-offset", type=int, default=0, help="The Message ID where your manual placeholders (blank messages) start")
    parser.add_argument("--video-dir", type=str, help="Path to the video files for date-sorting")
    parser.add_argument("--force-user", action="store_true", help="Use your personal account instead of the bot for restricted channels")
    args = parser.parse_args()

    # Priority: CLI arg > Env var
    video_dir = args.video_dir or VIDEO_DIR
    run_now = args.run_now or RUN_NOW
    only_index = args.only_index or ONLY_INDEX
    index_offset = args.index_offset
    force_user = args.force_user

    files_sorted = load_video_files_sorted(video_dir)
    if not files_sorted:
        print("🗂️ VIDEO_DIR: (In this version, only message dates may be used)")

    app = create_pyrogram_client(force_user=force_user)
    try:
        await app.start()
    except Exception as e:
        if not force_user and "BOT_METHOD_INVALID" in str(e):
             print(f"⚠️ Bot failed ({e}). Falling back to User Mode...")
             app = create_pyrogram_client(force_user=True)
             await app.start()
        else:
             raise e

    try:
        chat_id, chat_title = await resolve_channel(app)
        if not chat_id:
            # Automatic Fallback if bot can't see the channel
            if not force_user and BOT_TOKEN:
                print("⚠️ Bot cannot see the channel (likely permission issue). Falling back to User Mode...")
                await app.stop()
                app = create_pyrogram_client(force_user=True)
                await app.start()
                chat_id, chat_title = await resolve_channel(app)

        if not chat_id:
            print("❌ No channel found or no access. Check .env parameters.")
            return

        print(f"📺 Target Channel: {chat_title} (ID: {chat_id})")

        videos = await get_all_videos_info(app, chat_id)
        
        # If offset is provided, we might want to filter or just use it for editing placeholders.
        # The user says "From message #2".
        
        await save_backup(videos)

        if only_index:
            print("🛈 ONLY_INDEX is active: No captions will be edited; only index post will be created/updated.")
            planned = plan_from_existing(videos, files_sorted)
        else:
            planned = plan_numbering_by_files(videos, files_sorted)
            await apply_updates(app, chat_id, planned, dry_run=not run_now)
            if not run_now:
                print("⚠️ No changes applied. To apply for real, use --run-now or set RUN_NOW=true in .env.")

        print(f"🧾 Generating/Updating Index Post (Offset: {index_offset})...")
        await create_index_posts(app, chat_id, planned, title="📚 Video List", start_offset=index_offset, dry_run=not run_now)
        

    finally:
        await app.stop()
        print("🔒 Connection closed.")

if __name__ == "__main__":
    asyncio.run(main())
