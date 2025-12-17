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
# اضافه کردن این متغیر به بخش تنظیمات
RENAME_FILES = os.getenv("RENAME_FILES", "").lower() in ("1", "true", "yes", "y")

if not API_ID or not API_HASH:
    raise ValueError("API_ID و API_HASH را در .env تنظیم کنید.")

SESSION_NAME = "caption_updater_bot" if BOT_TOKEN else "caption_updater_user"

# جهت‌دهی RTL/LTR
RLM = "\u200F"
LRM = "\u200E"
RTL_MARKS_RE = re.compile(r"[\u200e\u200f]")

# =========================== Title helpers ===========================
def clean_caption(caption: str) -> str:
    if not caption:
        return ""
    cleaned = caption.strip()
    # حذف هر شماره‌گذاری قدیمی
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
        print("🗂️ VIDEO_DIR تنظیم نشده.")
        return result
    root = Path(video_dir).expanduser().resolve()
    print(f"🗂️ VIDEO_DIR: {root} (برای تاریخ ساخت فایل‌ها)")
    if not root.exists():
        print("⚠️ VIDEO_DIR وجود ندارد.")
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
        print("🤖 حالت Bot فعال است.")
        return Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)
    else:
        print("👤 حالت User فعال است.")
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
                print("ℹ️ قبلاً عضو کانال بوده‌اید.")
            else:
                print(f"⚠️ join_chat: {e}")
        try:
            chat = await app.get_chat(INVITE_LINK)
            if is_channel_like(chat.type):
                print(f"✅ هدف از INVITE_LINK: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ INVITE_LINK به {chat.type} اشاره می‌کند.")
        except Exception as e:
            print(f"⚠️ get_chat(INVITE_LINK): {e}")

    # 2) CHANNEL_ID
    if CHANNEL_ID_ENV:
        try:
            cid = int(CHANNEL_ID_ENV)
            chat = await app.get_chat(cid)
            if is_channel_like(chat.type):
                print(f"✅ هدف از CHANNEL_ID: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ CHANNEL_ID به {chat.type} اشاره می‌کند.")
        except Exception as e:
            print(f"⚠️ CHANNEL_ID نامعتبر/بدون دسترسی: {e}")

    # 3) CHANNEL_USERNAME
    if CHANNEL_USERNAME:
        try:
            chat = await app.get_chat(CHANNEL_USERNAME)
            if is_channel_like(chat.type):
                print(f"✅ هدف از CHANNEL_USERNAME: {chat.title} (ID: {chat.id})")
                return chat.id, chat.title
            else:
                print(f"⚠️ {CHANNEL_USERNAME} => {chat.type}")
        except Exception as e:
            print(f"⚠️ CHANNEL_USERNAME نامعتبر/بدون دسترسی: {e}")

    # 4) fallback
    print("🔍 جستجو بین دیالوگ‌ها برای یافتن کانالی که ویدیو دارد ...")
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
            print(f"✅ انتخاب شد: {best[2]} (ID: {best[1]}) ویدیوها: {best[0]}")
            return best[1], best[2]
    except Exception as e:
        print(f"⚠️ خطا در get_dialogs(): {e}")

    return None, None

# =========================== Fetch & Plan ===========================
async def get_all_videos_info(app: Client, chat_id: int):
    videos = []
    checked = 0
    print("📥 درحال خواندن تاریخچه کانال...")
    async for m in app.get_chat_history(chat_id, limit=0):
        checked += 1
        if m.video:
            videos.append({
                "message_id": m.id,
                "caption": m.caption or "",
                "date": m.date if (m.date and m.date.tzinfo) else (m.date.replace(tzinfo=timezone.utc) if m.date else None),
            })
    print(f"✅ کل پیام‌های بررسی‌شده: {checked} | ویدیوها: {len(videos)}")
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
        print(f"💾 بکاپ ذخیره شد: {filename}")
    except Exception as e:
        print(f"⚠️ خطا در ذخیره بکاپ: {e}")

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
        print(f"🗂️ فایل‌های ویدئو شناخته‌شده: {len(files_sorted)}")
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
            print("🛈 تاریخ فایل‌ها در دسترس نیست؛ بر اساس تاریخ پیام مرتب شد.")
        else:
            print(f"🛈 شمار فایل‌ها با ویدیوها برابر نبود ({len(files_sorted)} ≠ {len(videos)}). از تاریخ پیام استفاده شد.")
        return planned

# =========================== Apply updates ===========================
async def apply_updates(app: Client, chat_id: int, planned, dry_run=True):
    ok, fail = 0, 0
    print(f"\n{'🔄 حالت تست (بدون اعمال)' if dry_run else '📝 اعمال واقعی'} | تعداد: {len(planned)}")
    for i, item in enumerate(planned, start=1):
        mid = item["message_id"]
        oldc = item["old_caption"]
        newc = item["new_caption"]
        sdt = item.get("sort_date")
        print(f"\n[{i}/{len(planned)}] msg_id={mid}")
        if sdt:
            print(f"  🗓️ sort_date: {sdt.isoformat() if isinstance(sdt, datetime) else sdt}")
        print(f"  📝 قبلی: {oldc}")
        print(f"  🆕 جدید: {newc}")
        if dry_run:
            ok += 1
            continue
        try:
            await app.edit_message_caption(chat_id, mid, newc, parse_mode=ParseMode.HTML)
            ok += 1
            await asyncio.sleep(0.7)
        except ChatAdminRequired:
            print("  ❌ نیاز به دسترسی ادمین برای ویرایش پیام‌های کانال.")
            fail += 1
        except RPCError as e:
            print(f"  ❌ خطا: {e}")
            fail += 1
            if "FLOOD" in str(e).upper():
                print("  ⏳ مکث 30 ثانیه...")
                await asyncio.sleep(30)
        except Exception as e:
            print(f"  ❌ خطای غیرمنتظره: {e}")
            fail += 1
    print(f"\n📊 نتیجه: موفق {ok} | ناموفق {fail}")
    return ok, fail

# =========================== Index posts ===========================
def tg_private_link(chat_id: int, message_id: int) -> str:
    internal = abs(chat_id) - 1000000000000
    return f"https://t.me/c/{internal}/{message_id}"

def safe_extract_number(new_caption: str) -> int:
    """شماره را از ابتدای کپشن استخراج می‌کند؛ RLM/LRM حذف می‌شوند."""
    if not new_caption:
        return 0
    s = RTL_MARKS_RE.sub("", new_caption)
    m = re.match(r"^\s*(\d{1,4})", s)
    return int(m.group(1)) if m else 0

async def create_index_posts(app: Client, chat_id: int, planned, title="📚 فهرست ویدیوها", per_post_limit=4090):
    # sort مطمئن
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
                print("📌 پست شاخص Pin شد.")
            except Exception:
                pass
            first_index_msg_id = msg.id
        # reset
        chunk_lines = []
        chunk_len = len(header)

    # ساخت بدنه
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

    # آخرین بافر
    await flush()
    print("✅ پست شاخص ارسال شد.")

def plan_from_existing(videos):
    # از شماره‌ی موجود در کپشن‌ها استفاده می‌کنیم؛ هیچ تغییری در کپشن‌ها داده نمی‌شود
    def extract_num(caption: str) -> int:
        s = RTL_MARKS_RE.sub("", caption or "")
        # بهتر است الگوهای مختلف شماره‌گذاری را بررسی کنیم
        patterns = [
            r'^\s*#?\s*0*(\d{1,4})\s*[-\.\:\|]',  # 016 - عنوان
            r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',      # 016 عنوان
            r'^\s*#?\s*0*(\d{1,4})\s*$',          # فقط 016
            r'^\s*\[\s*0*(\d{1,4})\s*\]',         # [016]
            r'^\s*\(\s*0*(\d{1,4})\s*\)',         # (016)
        ]
        for pattern in patterns:
            m = re.match(pattern, s)
            if m:
                return int(m.group(1))
        return 999999  # اگر شماره پیدا نشد، آخر لیست قرار بگیرد

    # فقط بر اساس شماره‌ی استخراج شده مرتب می‌کنیم
    vids_sorted = sorted(videos, key=lambda v: extract_num(v.get("caption", "")))

    planned = []
    for v in vids_sorted:
        planned.append({
            "message_id": v["message_id"],
            "old_caption": v["caption"] or "",
            "new_caption": v["caption"] or "",   # بدون تغییر
            "sort_date": v.get("date")
        })
    
    print(f"📋 ویدیوها بر اساس شماره کپشن مرتب شدند:")
    for i, item in enumerate(planned[:5]):  # نمایش 5 تای اول برای بررسی
        num = extract_num(item["old_caption"])
        print(f"  {i+1}. شماره: {num} | کپشن: {item['old_caption'][:50]}...")
    
    return planned


# اضافه کردن این تابع به کد اصلی

def extract_number_from_caption(caption: str) -> int:
    """استخراج شماره از کپشن با الگوهای مختلف"""
    if not caption:
        return 999999
    
    s = RTL_MARKS_RE.sub("", caption)
    patterns = [
        r'^\s*#?\s*0*(\d{1,4})\s*[-\.\:\|]',  # 016 - عنوان
        r'^\s*#?\s*0*(\d{1,4})\s*[^\d]',      # 016 عنوان  
        r'^\s*#?\s*0*(\d{1,4})\s*$',          # فقط 016
        r'^\s*\[\s*0*(\d{1,4})\s*\]',         # [016]
        r'^\s*\(\s*0*(\d{1,4})\s*\)',         # (016)
    ]
    
    for pattern in patterns:
        m = re.match(pattern, s)
        if m:
            return int(m.group(1))
    return 999999

def clean_filename(text: str) -> str:
    """تمیز کردن متن برای استفاده در نام فایل"""
    if not text:
        return ""
    # حذف کاراکترهای غیرمجاز در نام فایل
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    # حذف فاصله‌های اضافی
    text = re.sub(r'\s+', ' ', text).strip()
    # محدود کردن طول
    return text[:100] if len(text) > 100 else text

async def rename_video_files_by_captions(videos, video_dir: str, dry_run=True):
    """تغییر نام فایل‌های ویدیو بر اساس شماره‌گذاری کپشن‌ها"""
    if not video_dir:
        print("⚠️ VIDEO_DIR تنظیم نشده است.")
        return
    
    root = Path(video_dir).expanduser().resolve()
    if not root.exists():
        print(f"⚠️ پوشه {root} وجود ندارد.")
        return
    
    # پیدا کردن فایل‌های ویدیو
    video_files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"):
            video_files.append(p)
    
    print(f"🎬 تعداد فایل‌های ویدیو پیدا شده: {len(video_files)}")
    print(f"📺 تعداد ویدیوهای کانال: {len(videos)}")
    
    if len(video_files) != len(videos):
        print("⚠️ تعداد فایل‌های ویدیو با ویدیوهای کانال برابر نیست!")
        response = input("آیا می‌خواهید ادامه دهید؟ (y/N): ")
        if response.lower() not in ['y', 'yes']:
            return
    
    # مرتب‌سازی ویدیوهای کانال بر اساس شماره کپشن
    videos_sorted = sorted(videos, key=lambda v: extract_number_from_caption(v.get("caption", "")))
    
    # مرتب‌سازی فایل‌ها بر اساس تاریخ ساخت
    files_with_dates = []
    for p in video_files:
        dt = get_file_timestamp(p)
        if dt:
            files_with_dates.append((p, dt))
    
    files_sorted = sorted(files_with_dates, key=lambda x: x[1])
    
    print(f"\n{'🔄 حالت تست (بدون تغییر نام)' if dry_run else '📝 تغییر نام واقعی'}")
    print("-" * 80)
    
    renamed_count = 0
    for i, (video_info, (file_path, _)) in enumerate(zip(videos_sorted, files_sorted)):
        caption = video_info.get("caption", "")
        number = extract_number_from_caption(caption)
        
        # استخراج عنوان از کپشن
        clean_cap = clean_caption(caption)
        title = clean_filename(clean_cap) if clean_cap else "untitled"
        
        # ساخت نام جدید
        old_name = file_path.name
        extension = file_path.suffix
        new_name = f"{number:03d} - {title}{extension}"
        new_path = file_path.parent / new_name
        
        print(f"\n[{i+1}/{len(files_sorted)}]")
        print(f"  📄 قبلی: {old_name}")
        print(f"  🆕 جدید: {new_name}")
        print(f"  📝 کپشن: {caption[:60]}{'...' if len(caption) > 60 else ''}")
        
        # بررسی تکراری بودن نام
        if new_path.exists() and new_path != file_path:
            print(f"  ⚠️ فایل با نام جدید قبلاً وجود دارد!")
            continue
        
        if not dry_run:
            try:
                file_path.rename(new_path)
                print(f"  ✅ تغییر نام موفق")
                renamed_count += 1
            except Exception as e:
                print(f"  ❌ خطا در تغییر نام: {e}")
        else:
            renamed_count += 1
    
    print(f"\n📊 نتیجه: {renamed_count} فایل {'قابل تغییر نام' if dry_run else 'تغییر نام یافت'}")
    
    if dry_run:
        print("\n⚠️ برای اعمال واقعی تغییرات، RENAME_FILES=true را در .env اضافه کنید.")



# =========================== Main ===========================
async def main():
    files_sorted = load_video_files_sorted(VIDEO_DIR)
    if not files_sorted:
        print("🗂️ VIDEO_DIR: (در این نسخه ممکن است فقط تاریخ پیام‌ها مبنا شود)")

    app = create_pyrogram_client()
    await app.start()
    try:
        chat_id, chat_title = await resolve_channel(app)
        if not chat_id:
            print("❌ هیچ کانالی پیدا نشد/دسترسی نیست. پارامترهای .env را بررسی کن.")
            return

        print(f"📺 کانال هدف: {chat_title} (ID: {chat_id})")

        videos = await get_all_videos_info(app, chat_id)
        await save_backup(videos)

        if ONLY_INDEX:
            print("🛈 ONLY_INDEX فعال است: هیچ کپشنی ویرایش نمی‌شود؛ فقط پست شاخص ساخته/به‌روزرسانی می‌شود.")
            planned = plan_from_existing(videos)
        else:
            files_sorted = load_video_files_sorted(VIDEO_DIR)
            planned = plan_numbering_by_files(videos, files_sorted)
            # مرحله تست/اعمال فقط وقتی ONLY_INDEX غیرفعال است
            await apply_updates(app, chat_id, planned, dry_run=not RUN_NOW)
            if not RUN_NOW:
                print("⚠️ تغییری اعمال نشد. برای اعمال واقعی RUN_NOW=true را در .env قرار بده.")

        print("🧾 ساخت پست شاخص ...")
        await create_index_posts(app, chat_id, planned, title="📚 فهرست ویدیوها")
        if VIDEO_DIR:
            print("\n🎬 شماره‌گذاری فایل‌های ویدیو ...")
            await rename_video_files_by_captions(videos, VIDEO_DIR, dry_run=not RENAME_FILES)


    finally:
        await app.stop()
        print("🔒 اتصال بسته شد.")

if __name__ == "__main__":
    asyncio.run(main())
