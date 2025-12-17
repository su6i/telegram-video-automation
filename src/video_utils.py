import os
import subprocess
import json
import math
import os
import re
from PIL import Image, ImageDraw, ImageFont
import textwrap

# حد آستانه تقسیم (45MB)
SIZE_THRESHOLD_MB = 45
BOT_MAX_SIZE_MB = 45
USER_MAX_SIZE_MB = 1900  # 1.9GB

def get_video_info(input_path):
    """دریافت اطلاعات کامل ویدیو"""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", 
            "-show_format", "-show_streams", input_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            
            # یافتن stream ویدیو
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
        print(f"خطا در دریافت اطلاعات ویدیو: {str(e)}")
        return None

def get_smart_title(input_path):
    """
    استخراج هوشمند تیتر:
    ۱. تلاش برای خواندن تیتر از متادیتای فایل (اولویت بالا)
    ۲. اگر نبود، استفاده از اسم فایل و تمیزکاری آن
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
    
    # الگوی "Number - Title"
    if " - " in base_name:
        parts = base_name.split(" - ", 1)
        if len(parts) == 2:
            return parts[1].strip()
            
    # الگوی "Number_Title"
    # حذف پیشوند عددی اگر باشد (001_)
    clean_name = re.sub(r'^\d+[_ ]', '', base_name)
    # تبدیل _ به فاصله
    clean_name = clean_name.replace('_', ' ')
    
    return clean_name.strip()

def calculate_optimal_segments(file_size_mb, target_size_mb=40):
    """محاسبه تعداد بهینه قسمت‌ها برای ربات"""
    if file_size_mb <= target_size_mb:
        return 1
    
    # محاسبه تعداد قسمت‌ها با در نظر گیری 10% overhead
    segments = math.ceil(file_size_mb / (target_size_mb * 0.9))
    return segments

def create_intro_video(title, output_intro_path, font_path="src/fonts/Vazir-Bold.ttf"):
    """ساخت ویدیوی اینترو ۳ ثانیه‌ای از عنوان"""
    try:
        # تنظیمات تصویر
        width, height = 1920, 1080
        background_color = (0, 0, 0)
        text_color = (255, 255, 255)
        
        # ساخت تصویر
        img = Image.new('RGB', (width, height), color=background_color)
        draw = ImageDraw.Draw(img)
        
        # لود فونت
        try:
            font_size = 120
            font = ImageFont.truetype(font_path, font_size)
        except OSError:
            print(f"⚠️ فونت {font_path} پیدا نشد، از فونت پیش‌فرض استفاده می‌شود.")
            font = ImageFont.load_default()
            font_size = 40

        # تنظیم متن (Word Wrap)
        # تخمین تقریبی تعداد کاراکتر در هر خط
        chars_per_line = 25 
        lines = textwrap.wrap(title, width=chars_per_line)
        
        # محاسبه ارتفاع کل متن برای وسط‌چین کردن
        # در پیلوهای جدید, textbbox دقیق‌تر است اما برای سادگی فعلا تقریبی می‌رویم یا از getbbox
        # getbbox availability depends on version.
        # Let's use simple logic: line_height approx 1.5 * font_size
        line_height = int(font_size * 1.5)
        total_text_height = len(lines) * line_height
        
        current_y = (height - total_text_height) // 2
        
        for line in lines:
            # وسط‌چین افقی
            # draw.textlength is available in newer Pillow
            text_width = draw.textlength(line, font=font)
            current_x = (width - text_width) // 2
            
            draw.text((current_x, current_y), line, font=font, fill=text_color)
            current_y += line_height
            
        # ذخیره تصویر موقت
        temp_image = "temp_intro.png"
        img.save(temp_image)
        
        # تبدیل تصویر به ویدیو ۳ ثانیه‌ای با ffmpeg
        # -loop 1 -i image -t 3 ...
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", temp_image,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", # سکوت صوتی
            "-t", "2", # 2 ثانیه کافیست
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-shortest", 
            output_intro_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        # حذف تصویر موقت
        if os.path.exists(temp_image):
            os.remove(temp_image)
            
        return True
    except Exception as e:
        print(f"❌ خطا در ساخت اینترو: {e}")
        return False

def add_intro_to_video(video_path, title, output_path):
    """اضافه کردن اینترو به ابتدای ویدیو"""
    intro_path = "temp_intro_video.mp4"
    temp_concat_list = "concat_list.txt"
    
    try:
        # 1. ساخت اینترو
        if not create_intro_video(title, intro_path):
            return False
            
        # 2. اسکیل کردن اینترو به اندازه ویدیوی اصلی (اگر لازم باشد)
        # فعلا فرض می‌کنیم ویدیو اصلی هم Aspect Ratio استاندارد دارد یا پلیر هندل می‌کند.
        # برای اطمینان بهتر است اینترو را به رزولوشن ویدیو اصلی تبدیل کنیم، ولی فعلا Re-encode کلی می‌کنیم.
        
        # روش Concat Demuxer (سریعتر اما نیاز به کدک یکسان دارد)
        # بنابراین باید اینترو را بسازیم و بعد همه را Encode کنیم.
        # یا از filter_complex استفاده کنیم که مطمئن‌تر است.
        
        # بیایید از filter_complex استفاده کنیم که ریسایز را هم هندل کند.
        # [0:v] [1:v] concat=n=2:v=1:a=1 [v] [a]
        
        # اما برای سادگی و پرفورمنس، بیایید فرض کنیم می خواهیم خروجی نهایی استاندارد باشد.
        
        # استراتژی: 
        # ما در process_safe در حال re-encode هستیم. پس می‌توانیم همانجا این کار را انجام دهیم.
        # اما اگر بخواهیم جدا انجام دهیم دوباره کاری است.
        # بیایید تابع process را تغییر دهیم که این کار را بکند.
        pass 
        
    except Exception as e:
        print(f"Error adding intro: {e}")
        return False

async def process_video_for_bot_safe(input_path, output_path, title):
    """پردازش ویدیو برای ربات (نسخه ایمن‌تر) + اینترو"""
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"🤖 پردازش برای ربات - {title}")
        print(f"   📏 اندازه اصلی: {file_size_mb:.2f}MB")
        
        intro_path = f"intro_{os.path.basename(input_path)}"
        
        # ساخت اینترو
        intro_created = create_intro_video(title, intro_path)
        
        if intro_created:
            print("   🎞️ اینترو ساخته شد.")
            # استفاده از filter_complex برای چسباندن
            # ما نیاز داریم ورودی‌ها را اسکیل کنیم تا هم‌اندازه شوند (1280x720 مثلا برای ربات خوبه)
            # scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2
            
            # برای اطمینان، هر دو را به یک سایز مشخص می‌بریم (مثلا HD Ready)
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
            print("   ⚠️ خطا در ساخت اینترو، ادامه بدون اینترو...")
            # فال‌بک به پردازش معمولی
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
            timeout=900 # 15 دقیقه (چون re-encode است)
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ خطای ffmpeg (کد {result.returncode}):")
            print(f"   📝 stderr: {result.stderr[-300:]}")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   ✅ پردازش موفق - اندازه: {new_size:.2f}MB")
            return True
        
        return False
        
    except Exception as e:
        print(f"   ❌ خطا در پردازش: {str(e)}")
        # Cleanup intro if exists
        #if os.path.exists(intro_path): os.remove(intro_path)
        return False

async def process_video_for_user_safe(input_path, output_path, title):
    """پردازش ویدیو برای اکانت کاربری (همراه با اینترو)"""
    try:
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        
        print(f"👤 پردازش برای اکانت کاربری - {title}")
        print(f"   📏 اندازه اصلی: {file_size_mb:.2f}MB")
        
        intro_path = f"intro_user_{os.path.basename(input_path)}"
        intro_created = create_intro_video(title, intro_path)
        
        if intro_created:
             # برای یوزر اکانت کیفیت بالاتر (1920x1080)
            target_w, target_h = 1920, 1080
            
            # نکته: اگر ویدیو اصلی صدا نداشته باشد concat fail می‌شود؟ 
            # ما در create_intro_video صدای سکوت اضافه کردیم.
            # ویدیوهای آموزشی معمولا صدا دارند.
            
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
                "-preset", "medium", # سریع‌تر
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                output_path
            ]
        else:
             # اگر اینترو نشد، فقط کپی می‌کنیم (مانند قبل)
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
            timeout=1800  # 30 دقیقه
        )
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
        
        if result.returncode != 0:
            print(f"   ❌ خطای ffmpeg (کد {result.returncode}):")
            print(f"   📝 stderr: {result.stderr[-300:]}")
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"   ✅ پردازش موفق - اندازه: {new_size:.2f}MB")
            return True
        
        return False
        
    except Exception as e:
        print(f"   ❌ خطا در پردازش: {str(e)}")
        return False

async def split_video_for_bot_safe(input_path, output_dir, title, target_size_mb=40):
    """تقسیم ویدیو برای ربات + اضافه کردن اینترو به قسمت اول"""
    try:
        video_info = get_video_info(input_path)
        if not video_info or video_info['duration'] <= 0:
            return []
        
        file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
        duration = video_info['duration']
        segments = calculate_optimal_segments(file_size_mb, target_size_mb)
        
        print(f"✂️ تقسیم برای ربات به {segments} قسمت...")
        
        segment_duration = duration / segments
        output_files = []
        
        # ساخت اینترو اصلی یکبار
        intro_path = f"intro_split_{os.path.basename(input_path)}"
        intro_created = create_intro_video(title, intro_path)
        
        for i in range(segments):
            start_time = i * segment_duration
            safe_title = re.sub(r'[^\w\-_\s]', '_', title)
            # قسمت اول "intro_" نامیده می‌شود تا بدانیم اینترو دارد؟ نه، فقط خروجی نهایی
            output_path = os.path.join(output_dir, f"{safe_title}_bot_part{i+1:02d}.mp4")
            
            print(f"   📹 قسمت {i+1}/{segments}...")
            
            # اگر قسمت اول است و اینترو داریم -> Concat
            if i == 0 and intro_created:
                 # باید قسمت اول را ببریم، سپس با اینترو ترکیب کنیم
                 # این کار با یک دستور پیچیده می‌شود.
                 # بهتر است ابتدا ویدیو را Split کنیم، سپس اینترو را به قسمت اول بچسبانیم؟
                 # یا در همان دستور انجام دهیم.
                 
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
                # قسمت‌های بعدی بدون اینترو
                # فقط re-encode ساده (یا کپی؟ نه برای اسپلیت دقیق re-encode بهتر است)
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
                    print(f"   ✅ قسمت {i+1} آماده - {part_size:.2f}MB")
                    output_files.append(output_path)
                else:
                    print(f"   ❌ خطا در قسمت {i+1}: {result.stderr[-200:] if result.stderr else 'نامشخص'}")
                
            except subprocess.TimeoutExpired:
                print(f"   ⏰ timeout در قسمت {i+1}")
                continue
            except Exception as e:
                print(f"   ❌ خطا در قسمت {i+1}: {str(e)}")
                continue
        
        if intro_created and os.path.exists(intro_path):
            os.remove(intro_path)
            
        return output_files
        
    except Exception as e:
        print(f"❌ خطا در تقسیم: {str(e)}")
        if 'intro_path' in locals() and os.path.exists(intro_path): os.remove(intro_path)
        return []

def normalize_title(title):
    """تطبیق عنوان برای مقایسه"""
    # حذف کاراکترهای اضافی و نرمال‌سازی
    title = title.strip()
    title = re.sub(r'\s+', ' ', title)  # حذف فاصله‌های اضافی
    title = title.replace('ویدیو ', '')  # حذف پیشوند ویدیو
    title = title.replace('آموزش ', '')  # حذف پیشوند آموزش
    return title.lower()
