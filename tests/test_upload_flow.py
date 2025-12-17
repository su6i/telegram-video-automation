import os
import asyncio
from dotenv import load_dotenv
from src.video_utils import process_video_for_bot_safe

load_dotenv()

video_dir = "mongard_videos"
output_dir = "mongard_videos_processed"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def test_intro_generation():
    print("🧪 شروع تست ساخت ویدیو (بدون آپلود)...")
    
    filename = "001_اموزش پایتون مقدماتی.mp4"
    input_path = os.path.join(video_dir, filename)
    processed_path = os.path.join(output_dir, "preview_" + filename)
    
    if not os.path.exists(input_path):
        print(f"❌ فایل تست {input_path} پیدا نشد.")
        return

    # Title extraction
    title = filename.replace("001_", "").replace(".mp4", "").replace("_", " ")
    print(f"📝 تیتر تشخیص داده شده: {title}")
    
    print("⚙️ در حال ساخت ویدیو با اینترو...")
    # Using bot_safe logic which includes intro generation
    success = await process_video_for_bot_safe(input_path, processed_path, title)
    
    if success:
        print(f"✅ ویدیو با موفقیت ساخته شد: {processed_path}")
    else:
        print("❌ ساخت ویدیو شکست خورد.")

if __name__ == "__main__":
    asyncio.run(test_intro_generation())
