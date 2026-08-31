
import os
import subprocess
import json

STORAGE_DIR = ".storage"
TEMP_VIDEO_DIR = os.path.join(STORAGE_DIR, "temp_video")
OUTPUT_DIR = "output_720p"

def get_duration(path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except:
        return 0

def diagnose():
    print("🔍 Diagnosing Video Durations...")
    
    # 1. Check Temp Videos (Source)
    if os.path.exists(TEMP_VIDEO_DIR):
        files = [f for f in os.listdir(TEMP_VIDEO_DIR) if f.endswith(".mp4")]
        print(f"\n📂 Source Files in {TEMP_VIDEO_DIR}:")
        for f in sorted(files)[:5]:
            d = get_duration(os.path.join(TEMP_VIDEO_DIR, f))
            print(f"   📄 {f}: {d:.2f} seconds")

    # 2. Check Output Videos (Processed)
    if os.path.exists(OUTPUT_DIR):
        files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".mp4")]
        print(f"\n📂 Processed Files in {OUTPUT_DIR}:")
        for f in sorted(files)[:5]:
            d = get_duration(os.path.join(OUTPUT_DIR, f))
            print(f"   ✅ {f}: {d:.2f} seconds")

if __name__ == "__main__":
    diagnose()
