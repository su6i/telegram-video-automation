import os
import concurrent.futures
from tqdm import tqdm
import threading
import yt_dlp
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scrapers.site_scraper import SiteScraper

# پوشه برای ذخیره ویدیوها
output_dir = "downloads"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# فایل برای ذخیره لینک‌ها
output_file = "videos.txt"

# قفل برای چاپ
print_lock = threading.Lock()

def download_video(video_url, title, index, total, pbar):
    """دانلود ویدیو با yt-dlp و نمایش پیشرفت با tqdm"""
    # حذف کاراکترهای غیرمجاز از عنوان
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        title = title.replace(char, "_")
    
    # اضافه کردن شماره به فایل برای حفظ ترتیب
    filename = f"{index:03d}_{title}.mp4"
    output_path = os.path.join(output_dir, filename)
    
    if os.path.exists(output_path):
        with print_lock:
            print(f"فایل {filename} قبلاً دانلود شده است. نادیده گرفته شد.")
        pbar.update(1)
        return

    ydl_opts = {
        "outtmpl": output_path,
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "progress_hooks": [lambda d: update_progress(d, pbar)],
        "quiet": True,
        "no_warnings": True
    }
    
    try:
        with print_lock:
            print(f"شروع دانلود {index}/{total}: {title}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        with print_lock:
            print(f"✅ دانلود کامل شد: {filename}")
    except Exception as e:
        with print_lock:
            print(f"❌ خطا در دانلود {filename}: {str(e)}")
    finally:
        pbar.update(1)

def update_progress(d, pbar):
    """به‌روزرسانی پروگرس بار"""
    if d['status'] == 'downloading':
        total_bytes = d.get('total_bytes', d.get('total_bytes_estimate', 0))
        downloaded_bytes = d.get('downloaded_bytes', 0)
        if total_bytes > 0:
            pbar.total = total_bytes // 1024 // 1024  # MB
            pbar.n = downloaded_bytes // 1024 // 1024  # MB
            pbar.refresh()
    elif d['status'] == 'finished':
        pbar.n = pbar.total or 0
        pbar.refresh()

def main():
    print("🚀 شروع عملیات اسکرپینگ...")
    
    # 1. Scrape (Generic Architecture)
    # اینجا می‌توانید اسکرپر دیگری را انتخاب کنید
    scraper = SiteScraper()
    videos = scraper.get_video_links()
    
    if not videos:
        print("❌ هیچ ویدیویی پیدا نشد.")
        return

    print(f"✅ تعداد {len(videos)} ویدیو پیدا شد (مرتب‌شده بر اساس تاریخ).")
    
    # 2. Save Links to File
    with open(output_file, "w", encoding="utf-8") as f:
        for v in videos:
            f.write(f"{v['title']}\t{v['url']}\t{v.get('date', 'NoDate')}\n")
    print(f"📝 لینک‌ها در {output_file} ذخیره شدند.")

    # 3. Download
    total_videos = len(videos)
    max_workers = 3
    
    print(f"⬇️ شروع دانلود {total_videos} ویدیو...")
    
    with tqdm(total=total_videos, desc="کل پیشرفت", unit="فایل") as total_pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            # enumerate از 1 شروع می‌شود تا شماره‌گذاری درست باشد (001, 002...)
            for i, video in enumerate(videos, 1):
                if not video['url']:
                    continue
                
                pbar = tqdm(total=100, desc=f"{i:03d} {video['title'][:15]}...", unit="MB", leave=False)
                futures.append(
                    executor.submit(
                        download_video, 
                        video['url'], 
                        video['title'], 
                        i, 
                        total_videos, 
                        pbar
                    )
                )
            concurrent.futures.wait(futures)

    print("\n🎉 تمام عملیات به پایان رسید.")

if __name__ == "__main__":
    main()