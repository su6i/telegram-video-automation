import os
import asyncio
from dotenv import load_dotenv
from src.video_utils import process_video_for_user_safe, get_smart_title

load_dotenv()
# Config
video_dir = "downloads"
output_dir = "processed"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def manual_process():
    filename = "004 - Beautiful data visualization with Python pprint module.mp4"
    if not os.path.exists(os.path.join(video_dir, filename)):
         # Case-insensitive or partial match
         files = os.listdir(video_dir)
         for f in files:
             if "004" in f:
                 filename = f
                 break
    
    input_path = os.path.join(video_dir, filename)
    output_path = os.path.join(output_dir, filename) 
    
    if not os.path.exists(input_path):
        print(f"❌ Input file {input_path} does not exist.")
        return

    # Title extraction (Smart: Metadata > Filename)
    title = get_smart_title(input_path)

    print(f"🎬 Extracted Title (Smart): {title}")
    print(f"📂 Input: {input_path}")
    print(f"📂 Output: {output_path}")
    
    # Process
    success = await process_video_for_user_safe(input_path, output_path, title)
    
    if success:
        print(f"✅ Final video created successfully.")
        print(f"📍 File path: {output_path}")
        print("This file is now ready for upload.")
    else:
        print("❌ Processing failed.")

if __name__ == "__main__":
    asyncio.run(manual_process())
