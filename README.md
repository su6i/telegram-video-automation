# Telegram Video Automation Kit 🚀

A professional, generic framework for automated course scraping, video processing, and Telegram distribution. This tool handles the entire pipeline from extracting site content to delivering high-quality, optimized videos to your Telegram channel.

---

## 🏗️ Core Workflow

The system operates in three distinct phases, coordinated by a local manifest system.

### 1. Scan Phase (`./scan.sh`)
The scanning engine identifies the course structure (modules, lessons, resources) and builds a local manifest in `.storage/downloaded_video.txt`.
- **Delta Tracking**: Automatically detects new content based on already existing entries.
- **Metadata Extraction**: Scrapes lesson descriptions, external resources, and sub-titles.
- **Resume Capability**: Fast scans that only update missing or changed entries.

### 2. Download Phase (`./download.sh`)
The downloader fetches files based on the manifest entries.
- **Auto-Organization**: Files are saved into `downloads/CourseName/SectionName/` via a predictable index-based naming convention (e.g., `001_LessonTitle.mp4`).
- **Parallel Processing**: Supports multi-threaded downloads for high-speed acquisition.
- **Integrity**: Skips files that are already fully downloaded.

### 3. Upload Phase (`python3 scripts/process_and_upload.py`)
The uploader processes the media for optimal Telegram playback and delivers it with rich captions.

#### 🛠️ Technical Processing
- **Normalization**: All videos are re-encoded to 25 FPS with standard H.264 profiles and normalized AAC audio (44.1kHz stereo).
- **Resolution Control**: Default re-encoding to 720p for fast playback. Use the `--res` switch for custom quality.
- **Smart Thumbnails**: Extracts a high-quality representative frame (at 5s) to ensure professional-looking message previews.
- **Intros**: Optional `--intro` switch to generate and prepend a dynamic 3-second title card to every video.

#### 🤖 Hybrid Delivery
- **Bot Mode**: Uses the Bot API for files up to 50MB (fast, official).
- **User Mode**: Switches to a Pyrogram-based User Account for library-quality files up to 2GB.
- **Auto-Splitting**: Automatically segments files that exceed Telegram's size limits to ensure no content is skipped.

---

## 🚀 Quick Start

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   brew install ffmpeg  # or your OS equivalent
   ```

2. **Configuration**:
   Copy `.env.example` to `.env` and configure your API credentials and target channel.

3. **Execution**:
   ```bash
   bash scan.sh        # Create the manifest
   bash download.sh    # Download the videos
   python3 scripts/process_and_upload.py --res 720 --intro
   ```

---

## ⚙️ Advanced CLI Options

### `process_and_upload.py`
- `--res [720|1080]`: Set target resolution (Default: 720).
- `--intro`: Prepend a generated title card to each video.
- `--video-dir PATH`: Manually specify a source directory for video files.

### `update_captions.py`
- Synchronizes local numbering with Telegram captions and generates a pinned Index Post listing all content with internal message links.

---

*Generic automation framework for video processing and distribution.*
