import os
import subprocess
import json
import math
import os
import re
import shutil
from PIL import Image, ImageDraw, ImageFont
import textwrap

# Threshold for splitting (45MB)
SIZE_THRESHOLD_MB = 45
BOT_MAX_SIZE_MB = 45
USER_MAX_SIZE_MB = 1900  # 1.9GB

# Cache for hardware encoder detection
_hw_encoder_cache = None

def detect_hw_encoder():
    """
    Auto-detect available hardware encoder.
    Returns the best available encoder with automatic fallback.
    
    Priority:
    1. h264_videotoolbox (Apple Silicon / Intel Mac - very fast)
    2. h264_nvenc (NVIDIA GPU)
    3. h264_qsv (Intel QuickSync)
    4. libx264 (CPU fallback - always works)
    """
    global _hw_encoder_cache
    
    if _hw_encoder_cache is not None:
        return _hw_encoder_cache
    
    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True, text=True, timeout=10
        )
        encoders = result.stdout
        
        # Check in priority order
        if 'h264_videotoolbox' in encoders:
            _hw_encoder_cache = 'h264_videotoolbox'
            print("⚡ Hardware acceleration: Apple VideoToolbox detected")
        elif 'h264_nvenc' in encoders:
            _hw_encoder_cache = 'h264_nvenc'
            print("⚡ Hardware acceleration: NVIDIA NVENC detected")
        elif 'h264_qsv' in encoders:
            _hw_encoder_cache = 'h264_qsv'
            print("⚡ Hardware acceleration: Intel QuickSync detected")
        else:
            _hw_encoder_cache = 'libx264'
            print("ℹ️ Using CPU encoding (libx264)")
            
    except Exception:
        _hw_encoder_cache = 'libx264'
        print("ℹ️ Using CPU encoding (libx264)")
    
    return _hw_encoder_cache

def check_disk_space(required_mb, path='.'):
    """Check if enough disk space is available."""
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= required_mb * 1.5  # 1.5x safety margin
    except:
        return True  # Assume OK if can't check

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
        # print(f"Error getting video info: {str(e)}") # Suppress noise
        return None

def is_video_valid(video_path):
    """Check if video file is valid and can be opened by ffmpeg/ffprobe."""
    if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
        return False
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except:
        return False

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

def extract_thumbnail(video_path, output_thumb_path, timestamps=["00:00:05", "00:00:01", "00:00:10"]):
    """
    Extract a thumbnail from the video. 
    Tries multiple timestamps if one fails.
    """
    for ts in timestamps:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", ts,
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                output_thumb_path
            ]
            # Use capture_output to keep logs clean
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and os.path.exists(output_thumb_path) and os.path.getsize(output_thumb_path) > 0:
                return True
        except:
            continue
    return False

def add_intro_to_video(video_path, title, output_path):
    """Add intro to the beginning of the video."""
    intro_path = "temp_intro_video.mp4"
    temp_concat_list = "concat_list.txt"
    
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



async def process_video_for_bot_safe(input_path, output_path, title, add_intro=False, target_res=720):
    """
    Process video for bot (safer version) + optional intro
    ✅ استفاده کامل filter_complex + صحیح stream selection
    ✅ بهتر error handling و logging
    """
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"🤖 Processing for bot - {title}")
        print(f"   📏 Original size: {file_size_mb:.2f}MB")
        
        intro_created = False
        intro_path = f"intro_{os.path.basename(input_path)}"

        if add_intro:
            intro_created = create_intro_video(title, intro_path)
        
        # تعیین resolution
        if target_res == 1080:
            target_w, target_h = 1920, 1080
        else:
            target_w, target_h = 1280, 720
        
        if intro_created:
            print("   🎞️ Intro created - re-encoding required...")
            
            # ✅ Auto-detect hardware encoder
            encoder = detect_hw_encoder()
            
            # ✅ filter_complex برای concat intro + main video
            process_cmd = [
                "ffmpeg", "-y",
                "-i", intro_path,
                "-i", input_path,
                "-filter_complex", 
                f"[0:v:0]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                f"[1:v:0]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                f"[0:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
                f"[1:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
                f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", encoder,  # ✅ Auto hardware acceleration
                "-c:a", "aac",
            ]
            # Add encoder-specific options
            if encoder == 'libx264':
                process_cmd.extend(["-preset", "fast", "-crf", "23"])
            elif encoder == 'h264_videotoolbox':
                process_cmd.extend(["-q:v", "65"])  # Quality for VideoToolbox
            else:
                process_cmd.extend(["-preset", "fast"])
            
            process_cmd.extend([
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ])
        else:
            # ✅ No intro: ALWAYS re-encode to target resolution
            orig_info = get_video_info(input_path)
            orig_w = orig_info.get('width', 1920) if orig_info else 1920
            orig_h = orig_info.get('height', 1080) if orig_info else 1080
            
            print(f"   🔄 Re-encoding {orig_w}x{orig_h} → {target_w}x{target_h}...")
            encoder = detect_hw_encoder()
            
            process_cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", f"fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-c:v", encoder,
                "-c:a", "aac",
                "-ar", "44100",
                "-ac", "2",
            ]
            if encoder == 'libx264':
                process_cmd.extend(["-preset", "fast", "-crf", "23"])
            elif encoder == 'h264_videotoolbox':
                process_cmd.extend(["-q:v", "65"])
            else:
                process_cmd.extend(["-preset", "fast"])
            
            process_cmd.extend([
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ])
        
        # ✅ Show ffmpeg progress in terminal
        result = subprocess.run(
            process_cmd, 
            stdout=None,  # Show output
            stderr=None,  # Show progress
            timeout=1200
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ ffmpeg error (code {result.returncode})")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            final_w, final_h, _ = get_video_info_detailed(output_path)
            print(f"   ✅ Success - Size: {new_size:.2f}MB, Final: {final_w}x{final_h}")
            return True
        else:
            print(f"   ❌ Output file not created or too small")
            return False
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ Processing timeout (20 minutes exceeded)")
        if 'intro_created' in locals() and intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        return False
    except Exception as e:
        print(f"   ❌ Processing error: {str(e)}")
        if 'intro_created' in locals() and intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        return False


async def process_video_for_user_safe(input_path, output_path, title, add_intro=False, target_res=720):
    """
    Process video for USER ACCOUNT (supports custom resolution: 720 or 1080)
    ✅ استفاده کامل filter_complex - metadata صحیح!
    ✅ صریح stream selection
    ✅ بهتر progress tracking و error handling
    
    Note: This function is for User Accounts!
    Bot accounts should use process_video_for_bot_safe (1280x720)
    """
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"👤 Processing for user account - {title}")
        print(f"   📏 Original size: {file_size_mb:.2f}MB")
        
        # ✅ Step 1: Detect aspect ratio
        orig_w, orig_h, sar = get_video_info_detailed(input_path)
        aspect_ratio = (orig_w / orig_h) if orig_h > 0 else 1.777
        print(f"   📐 Original: {orig_w}x{orig_h} | SAR: {sar} | Aspect: {aspect_ratio:.2f}")
        
        # ✅ USER ACCOUNT: HD (1280x720) یا 4K (1920x1080)
        # Portrait vs Landscape detection
        if aspect_ratio < 1:
            if target_res == 1080:
                target_w, target_h = 1080, 1920
            else:
                target_w, target_h = 720, 1280
            print(f"   🔄 Portrait detected - {target_w}x{target_h}")
        else:
            if target_res == 1080:
                target_w, target_h = 1920, 1080
            else:
                target_w, target_h = 1280, 720
            print(f"   🔄 Landscape detected - {target_w}x{target_h}")
        
        intro_path = f"intro_user_{os.path.basename(input_path)}"
        intro_created = False
        
        if add_intro:
            intro_created = create_intro_video(title, intro_path)
        
        if intro_created:
            # ✅ With intro: re-encode needed for concat
            print(f"   🎞️ Intro created - re-encoding required...")
            
            # ✅ Auto-detect hardware encoder
            encoder = detect_hw_encoder()
            
            process_cmd = [
                "ffmpeg", "-y",
                "-i", intro_path,
                "-i", input_path,
                "-filter_complex", 
                f"[0:v:0]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                f"[1:v:0]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                f"[0:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
                f"[1:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
                f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", encoder,  # ✅ Auto hardware acceleration
                "-c:a", "aac",
            ]
            # Add encoder-specific options
            if encoder == 'libx264':
                process_cmd.extend(["-preset", "fast", "-crf", "23"])
            elif encoder == 'h264_videotoolbox':
                process_cmd.extend(["-q:v", "65"])  # Quality for VideoToolbox
            else:
                process_cmd.extend(["-preset", "fast"])
            
            process_cmd.extend([
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ])
        else:
            # ✅ No intro: ALWAYS re-encode to target resolution
            print(f"   🔄 Re-encoding {orig_w}x{orig_h} → {target_w}x{target_h}...")
            encoder = detect_hw_encoder()
            
            process_cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", f"fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-c:v", encoder,
                "-c:a", "aac",
                "-ar", "44100",
                "-ac", "2",
            ]
            # Encoder-specific options
            if encoder == 'libx264':
                process_cmd.extend(["-preset", "fast", "-crf", "23"])
            elif encoder == 'h264_videotoolbox':
                process_cmd.extend(["-q:v", "65"])
            else:
                process_cmd.extend(["-preset", "fast"])
            
            process_cmd.extend([
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ])
        
        # ✅ Show ffmpeg progress in terminal (stdout=None, stderr=None)
        result = subprocess.run(
            process_cmd, 
            stdout=None,  # Show output
            stderr=None,  # Show progress
            timeout=1800
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ ffmpeg error (code {result.returncode})")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            final_w, final_h, _ = get_video_info_detailed(output_path)
            print(f"   ✅ Success - Size: {new_size:.2f}MB, Final: {final_w}x{final_h}")
            return True
        else:
            print(f"   ❌ Output file not created or too small")
            return False
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ Processing timeout (30 minutes exceeded)")
        if 'intro_created' in locals() and intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        return False
    except Exception as e:
        print(f"   ❌ Processing error: {str(e)}")
        if 'intro_created' in locals() and intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        return False



def get_video_sar(input_path):
    """Extract aspect ratio information, accounting for rotation."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,sample_aspect_ratio:stream_tags=rotate",
            "-of", "json",
            input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        
        if data['streams']:
            stream = data['streams'][0]
            width = int(stream.get('width', 1280))
            height = int(stream.get('height', 720))
            sar = stream.get('sample_aspect_ratio', '1:1')
            
            # Check for rotation
            tags = stream.get('tags', {})
            rotate = tags.get('rotate', '0')
            try:
                rotate = int(rotate)
            except:
                rotate = 0
                
            # If rotated 90 or 270 degrees, swap width and height
            if abs(rotate) == 90 or abs(rotate) == 270:
                width, height = height, width
                
            return width, height, sar
            
        return 1280, 720, '1:1'
    except:
        return 1280, 720, '1:1'

def get_video_info_detailed(input_path):
    """
    Extract width, height, SAR for valid scaling.
    Includes ROTATION check to correctly identify landscape videos stored vertically.
    """
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,sample_aspect_ratio:stream_tags=rotate",
            "-of", "json",
            input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        
        if data['streams']:
            stream = data['streams'][0]
            w = int(stream.get('width', 1280))
            h = int(stream.get('height', 720))
            sar = stream.get('sample_aspect_ratio', '1:1')
            
            # Rotation Check (Critical for phone videos)
            tags = stream.get('tags', {})
            rotate = tags.get('rotate', '0')
            try:
                rotate = int(rotate)
            except:
                rotate = 0
            
            if abs(rotate) == 90 or abs(rotate) == 270:
                w, h = h, w
                
            return w, h, sar
        return 1280, 720, '1:1'
    except:
        return 1280, 720, '1:1'
        
async def split_video_for_bot_safe(input_path, output_dir, title, target_size_mb=40, add_intro=False, target_res=720):
    """Split video for bot + optional intro to the first part."""
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
        intro_created = False
        intro_path = f"intro_split_{os.path.basename(input_path)}"

        if add_intro:
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
                 
                 if target_res == 1080:
                     target_w, target_h = 1920, 1080
                 else:
                     target_w, target_h = 1280, 720
                 
                 split_cmd = [
                    "ffmpeg", "-y",
                    "-i", intro_path,
                    "-ss", str(start_time), # seek in input 2 (index 1)
                    "-i", input_path,
                    "-t", str(segment_duration), # duration from seek point
                    "-filter_complex",
                    f"[0:v]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                    f"[1:v]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                    f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
                    f"[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
                    f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
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

async def split_video_for_user_safe(input_path, output_dir, title, target_size_mb=1900, add_intro=False, target_res=720):
    """Split video for user account if > 2GB (or 4GB for Premium)."""
    try:
        video_info = get_video_info(input_path)
        if not video_info or video_info['duration'] <= 0:
            return []
        
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        duration = video_info['duration']
        # Calculate segments (use same logic but with larger target)
        segments = math.ceil(file_size_mb / (target_size_mb * 0.95))
        
        if segments <= 1:
            return [] # No split needed
            
        print(f"✂️ Splitting for user account into {segments} parts...")
        
        segment_duration = duration / segments
        output_files = []
        
        intro_created = False
        intro_path = f"intro_user_split_{os.path.basename(input_path)}"
        if add_intro:
            intro_created = create_intro_video(title, intro_path)
            
        for i in range(segments):
            start_time = i * segment_duration
            safe_title = re.sub(r'[^\w\-_\s]', '_', title)
            output_path = os.path.join(output_dir, f"{safe_title}_part{i+1:02d}.mp4")
            
            print(f"   📹 Part {i+1}/{segments}...")
            
            if i == 0 and intro_created:
                # Need re-encode for concat with intro
                if target_res == 1080:
                    target_w, target_h = 1920, 1080
                else:
                    target_w, target_h = 1280, 720
                split_cmd = [
                    "ffmpeg", "-y",
                    "-i", intro_path,
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(segment_duration),
                    "-filter_complex",
                    f"[0:v]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];"
                    f"[1:v]fps=25,scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];"
                    f"[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
                    f"[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
                    f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]",
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-preset", "medium",
                    "-crf", "23",
                    "-movflags", "+faststart",
                    output_path
                ]
            else:
                # Try "copy" for faster results if no intro needed
                # Accurate splitting with copy (-ss before -i)
                split_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(segment_duration),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    output_path
                ]
            
            try:
                result = subprocess.run(split_cmd, capture_output=True, text=True, timeout=600)
                if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    part_size = os.path.getsize(output_path) / (1024 * 1024)
                    print(f"   ✅ Part {i+1} ready - {part_size:.2f}MB")
                    output_files.append(output_path)
                else:
                    print(f"   ❌ Error in part {i+1}: {result.stderr[-200:] if result.stderr else 'unknown'}")
            except Exception as e:
                print(f"   ❌ Error in part {i+1}: {str(e)}")
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
            
        return output_files
        
    except Exception as e:
        print(f"❌ Error during user split: {str(e)}")
        return []

def normalize_title(title):
    """Normalize title for comparison."""
    # Remove extra chars and normalize
    title = title.strip()
    title = re.sub(r'\s+', ' ', title)  # Remove extra spaces
    title = title.replace('Video ', '')  # Remove 'Video' prefix
    title = title.replace('Tutorial ', '')  # Remove 'Tutorial' prefix
    return title.lower()
