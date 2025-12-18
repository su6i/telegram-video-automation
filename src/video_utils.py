import os
import subprocess
import json
import math
import os
import re
from PIL import Image, ImageDraw, ImageFont
import textwrap

# Threshold for splitting (45MB)
SIZE_THRESHOLD_MB = 45
BOT_MAX_SIZE_MB = 45
USER_MAX_SIZE_MB = 1900  # 1.9GB

def get_video_info(input_path):
    """Get full video information."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", 
            "-show_format", "-show_streams", input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            
            # Find video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            duration = float(data.get('format', {}).get('duration', 0))
            bitrate = int(data.get('format', {}).get('bit_rate', 0))
            tags = data.get('format', {}).get('tags', {})
            meta_title = tags.get('title', '') or tags.get('TITLE', '')
            
            return {
                'duration': duration,
                'bitrate': bitrate,
                'width': video_stream.get('width', 0) if video_stream else 0,
                'height': video_stream.get('height', 0) if video_stream else 0,
                'codec': video_stream.get('codec_name', '') if video_stream else '',
                'fps': eval(video_stream.get('r_frame_rate', '0/1')) if video_stream else 0,
                'title': meta_title
            }
        
        return None
    except Exception as e:
        print(f"Error getting video info: {str(e)}")
        return None

def get_smart_title(input_path):
    """
    Smart title extraction:
    1. Try reading title from file metadata (high priority)
    2. If missing, use filename and clean it up
    """
    filename = os.path.basename(input_path)
    
    # 1. Check Metadata
    info = get_video_info(input_path)
    if info and info.get('title'):
        title = info['title'].strip()
        if title:
            return title
            
    # 2. Fallback to Filename
    # "004 - Title.mp4" -> "Title"
    # "001_Title_Name.mp4" -> "Title Name"
    base_name = os.path.splitext(filename)[0]
    
    # Pattern "Number - Title"
    if " - " in base_name:
        parts = base_name.split(" - ", 1)
        if len(parts) == 2:
            return parts[1].strip()
            
    # Pattern "Number_Title"
    # Remove numeric prefix if exists (001_)
    clean_name = re.sub(r'^\d+[_ ]', '', base_name)
    # Replace _ with space
    clean_name = clean_name.replace('_', ' ')
    
    return clean_name.strip()

def calculate_optimal_segments(file_size_mb, target_size_mb=40):
    """Calculate optimal number of segments for bot."""
    if file_size_mb <= target_size_mb:
        return 1
    
    # Calculate segments considering 10% overhead
    segments = math.ceil(file_size_mb / (target_size_mb * 0.9))
    return segments

def create_intro_video(title, output_intro_path, font_path="src/fonts/Vazir-Bold.ttf"):
    """Create a 3-second intro video from title."""
    try:
        # Image settings
        width, height = 1920, 1080
        background_color = (0, 0, 0)
        text_color = (255, 255, 255)
        
        # Create image
        img = Image.new('RGB', (width, height), color=background_color)
        draw = ImageDraw.Draw(img)
        
        # Load font
        try:
            font_size = 120
            font = ImageFont.truetype(font_path, font_size)
        except OSError:
            print(f"⚠️ Font {font_path} not found, using default font.")
            font = ImageFont.load_default()
            font_size = 40

        # Text settings (Word Wrap)
        # Approximate characters per line
        chars_per_line = 25 
        lines = textwrap.wrap(title, width=chars_per_line)
        
        # Calculate total text height for centering
        # In newer Pillow, textbbox is more accurate but keeping it simple for now
        # getbbox availability depends on version.
        # Let's use simple logic: line_height approx 1.5 * font_size
        line_height = int(font_size * 1.5)
        total_text_height = len(lines) * line_height
        
        current_y = (height - total_text_height) // 2
        
        for line in lines:
            # Horizontal centering
            # draw.textlength is available in newer Pillow
            text_width = draw.textlength(line, font=font)
            current_x = (width - text_width) // 2
            
            draw.text((current_x, current_y), line, font=font, fill=text_color)
            current_y += line_height
            
        # Save temporary image
        temp_image = "temp_intro.png"
        img.save(temp_image)
        
        # Convert image to 3-second video with ffmpeg
        # -loop 1 -i image -t 3 ...
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", temp_image,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", # Silence audio
            "-t", "2", # 2 seconds is enough
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-shortest", 
            output_intro_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Delete temporary image
        if os.path.exists(temp_image):
            os.remove(temp_image)
            
        return True
    except Exception as e:
        print(f"❌ Error creating intro: {e}")
        return False

def add_intro_to_video(video_path, title, output_path):
    """Add intro to the beginning of the video."""
    intro_path = "temp_intro_video.mp4"
    temp_concat_list = "concat_list.txt"
    
    try:
    try:
        # 1. Create intro
        if not create_intro_video(title, intro_path):
            return False
            
        # 2. Scale intro to match main video size (if needed)
        # We assume main video has standard Aspect Ratio or player handles it.
        # For better reliability, we should convert intro to main video resolution, but currently we are re-encoding everything.
        
        # Concat Demuxer method (faster but requires same codec)
        # So we must create intro and then encode everything.
        # Or use filter_complex which is safer.
        
        # Let's use filter_complex which handles resize too.
        # [0:v] [1:v] concat=n=2:v=1:a=1 [v] [a]
        
        # But for simplicity and performance, assume we want standard output.
        
        # Strategy: 
        # We are re-encoding in process_safe anyway. So we can do it there.
        # Doing it separately is redundant.
        pass 
        
    except Exception as e:
        print(f"Error adding intro: {e}")
        return False

async def process_video_for_bot_safe(input_path, output_path, title):
    """Process video for bot (safer version) + intro"""
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"🤖 Processing for bot - {title}")
        print(f"   📏 Original size: {file_size_mb:.2f}MB")
        
        intro_path = f"intro_{os.path.basename(input_path)}"
        
        # Create intro
        intro_created = create_intro_video(title, intro_path)
        
        if intro_created:
            print("   🎞️ Intro created.")
            # Use filter_complex for concatenation
            # We need to scale inputs to match (e.g., 1280x720 is good for bot)
            # scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2
            
            # For reliability, force both to a specific size (e.g. HD Ready)
            target_w, target_h = 1280, 720
            
            process_cmd = [
                "ffmpeg", "-y",
                "-i", intro_path,
                "-i", input_path,
                "-filter_complex", 
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v0];"
                f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
        else:
            print("   ⚠️ Error creating intro, continuing without intro...")
            # Fallback to normal processing
            process_cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
        
        result = subprocess.run(
            process_cmd, 
            capture_output=True, 
            text=True,
            timeout=900 # 15 minutes (since it's re-encode)
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ ffmpeg error (code {result.returncode}):")
            print(f"   📝 stderr: {result.stderr[-300:]}")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   ✅ Processing successful - Size: {new_size:.2f}MB")
            return True
        
        return False
        
    except Exception as e:
        print(f"   ❌ Processing error: {str(e)}")
        # Cleanup intro if exists
        #if os.path.exists(intro_path): os.remove(intro_path)
        return False

async def process_video_for_user_safe(input_path, output_path, title):
    """Process video for user account (with intro)"""
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"👤 Processing for user account - {title}")
        print(f"   📏 Original size: {file_size_mb:.2f}MB")
        
        intro_path = f"intro_user_{os.path.basename(input_path)}"
        intro_created = create_intro_video(title, intro_path)
        
        if intro_created:
             # Higher quality for user account (1920x1080)
            target_w, target_h = 1920, 1080
            
            # Note: If original video has no audio, concat might fail?
            # We added silent audio in create_intro_video.
            # Tutorial videos usually have audio.
            
            process_cmd = [
                "ffmpeg", "-y",
                "-i", intro_path,
                "-i", input_path,
                "-filter_complex", 
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v0];"
                f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", # Re-encoding is mandatory for concat filter
                "-c:a", "aac",
                "-preset", "medium", # Faster
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
        else:
             # If intro failed, just copy (like before)
            process_cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
        result = subprocess.run(
            process_cmd, 
            capture_output=True, 
            text=True,
            timeout=1800  # 30 minutes
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ ffmpeg error (code {result.returncode}):")
            print(f"   📝 stderr: {result.stderr[-300:]}")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   ✅ Processing successful - Size: {new_size:.2f}MB")
            return True
        
        return False
        
    except Exception as e:
        print(f"   ❌ Processing error: {str(e)}")
        return False

async def split_video_for_bot_safe(input_path, output_dir, title, target_size_mb=40):
    """Split video for bot + add intro to the first part."""
    try:
        video_info = get_video_info(input_path)
        if not video_info or video_info['duration'] <= 0:
            return []
        
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        duration = video_info['duration']
        segments = calculate_optimal_segments(file_size_mb, target_size_mb)
        
        print(f"✂️ Splitting for bot into {segments} parts...")
        
        segment_duration = duration / segments
        output_files = []
        
        # Create main intro once
        intro_path = f"intro_split_{os.path.basename(input_path)}"
        intro_created = create_intro_video(title, intro_path)
        
        for i in range(segments):
            start_time = i * segment_duration
            safe_title = re.sub(r'[^\w\-_\s]', '_', title)
            # First part named "intro_" to know it has intro? No, just final output
            output_path = os.path.join(output_dir, f"{safe_title}_bot_part{i+1:02d}.mp4")
            
            print(f"   📹 Part {i+1}/{segments}...")
            
            # If first part AND we have intro -> Concat
            if i == 0 and intro_created:
                 # Need to trim first part, then concat with intro
                 # Complex command needed.
                 # Better to split video first, then attach intro to part 1?
                 # Or do it in one command.
                 
                 # trim first part
                 # [0:v] -> intro
                 # [1:v] -> video (trimmed)
                 
                 target_w, target_h = 1280, 720
                 
                 split_cmd = [
                    "ffmpeg", "-y",
                    "-i", intro_path,
                    "-ss", str(start_time), # seek in input 2 (index 1)
                    "-i", input_path,
                    "-t", str(segment_duration), # duration from seek point
                    "-filter_complex",
                    f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v0];"
                    f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[v1];"
                    f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]",
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "medium",
                    "-crf", "23",
                    "-movflags", "+faststart",
                    output_path
                 ]
            else:
                # Next parts without intro
                # Just simple re-encode (or copy? No, re-encode is better for accurate split)
                split_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(segment_duration),
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "medium",
                    "-crf", "23",
                    "-movflags", "+faststart",
                    output_path
                ]
            
            try:
                result = subprocess.run(split_cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    part_size = os.path.getsize(output_path) / (1024 * 1024)
                    print(f"   ✅ Part {i+1} ready - {part_size:.2f}MB")
                    output_files.append(output_path)
                else:
                    print(f"   ❌ Error in part {i+1}: {result.stderr[-200:] if result.stderr else 'unknown'}")
                
            except subprocess.TimeoutExpired:
                print(f"   ⏰ Timeout in part {i+1}")
                continue
            except Exception as e:
                print(f"   ❌ Error in part {i+1}: {str(e)}")
                continue
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
            
        return output_files
        
    except Exception as e:
        print(f"❌ Error during split: {str(e)}")
        if 'intro_path' in locals() and os.path.exists(intro_path): os.remove(intro_path)
        return []

def normalize_title(title):
    """Normalize title for comparison."""
    # Remove extra chars and normalize
    title = title.strip()
    title = re.sub(r'\s+', ' ', title)  # Remove extra spaces
    title = title.replace('Video ', '')  # Remove 'Video' prefix
    title = title.replace('Tutorial ', '')  # Remove 'Tutorial' prefix
    return title.lower()
