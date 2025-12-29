import os
import asyncio
from dotenv import load_dotenv
from src.video_utils import process_video_for_bot_safe

load_dotenv()

video_dir = "sample_videos"
output_dir = "sample_videos_processed"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

async def test_intro_generation():
    print("🧪 Starting video creation test (No upload)...")
    
    filename = "001_Python_Basics_Training.mp4"
    input_path = os.path.join(video_dir, filename)
    processed_path = os.path.join(output_dir, "preview_" + filename)
    
    if not os.path.exists(input_path):
        print(f"❌ Test file {input_path} not found.")
        return

    # Title extraction
    title = filename.replace("001_", "").replace(".mp4", "").replace("_", " ")
    print(f"📝 Detected title: {title}")
    
    print("⚙️ Creating video with intro...")
    # Using bot_safe logic which includes intro generation
    success = await process_video_for_bot_safe(input_path, processed_path, title)
    
    if success:
        print(f"✅ Video created successfully: {processed_path}")
    else:
        print("❌ Video creation failed.")

if __name__ == "__main__":
    asyncio.run(test_intro_generation())
