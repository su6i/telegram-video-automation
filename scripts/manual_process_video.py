import os
import asyncio
from dotenv import load_dotenv
from src.video_utils import process_video_for_user_safe, get_smart_title

load_dotenv()
# تنظیمات
video_dir = "downloads"
output_dir = "processed"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def manual_process():
    filename = "004 - نمایش زیبای داده ها با ماژول pprint پایتون.mp4"
    if not os.path.exists(os.path.join(video_dir, filename)):
         # Maybe there is a hidden char or something, let's try to match by partial name if exact fails
         files = os.listdir(video_dir)
         for f in files:
             if "004" in f:
                 filename = f
                 break
    
    input_path = os.path.join(video_dir, filename)
    output_path = os.path.join(output_dir, filename) 
    
    if not os.path.exists(input_path):
        print(f"❌ فایل ورودی {input_path} وجود ندارد.")
        return

    # Title extraction (Smart: Metadata > Filename)
    title = get_smart_title(input_path)

    print(f"🎬 تیتر استخراج شده (هوشمند): {title}")
    print(f"📂 ورودی: {input_path}")
    print(f"📂 خروجی: {output_path}")
    
    # Process
    success = await process_video_for_user_safe(input_path, output_path, title)
    print(f"📂 ورودی: {input_path}")
    print(f"📂 خروجی: {output_path}")
    
    # Process
    success = await process_video_for_user_safe(input_path, output_path, title)
    
    if success:
        print(f"✅ ویدیو نهایی با موفقیت ساخته شد.")
        print(f"📍 مسیر فایل: {output_path}")
        print("حالا این فایل آماده آپلود است.")
    else:
        print("❌ پردازش شکست خورد.")

if __name__ == "__main__":
    asyncio.run(manual_process())
