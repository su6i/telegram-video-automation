# 📺 Telegram Video Automation Kit

**A modular, robust, and automated pipeline to scrape, process, and upload videos to Telegram Channels.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Pyrogram-2CA5E0?style=flat-square&logo=telegram)](https://docs.pyrogram.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required-green?style=flat-square&logo=ffmpeg)](https://ffmpeg.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

## 📖 Overview

Are you managing a video archive channel on Telegram? Doing it manually is painful: downloading, checking files, adding captions/intros, and dealing with Telegram's upload limits.

**Telegram Video Automation Kit** solves this by providing a unified workflow:
1.  **🔌 Scrape**: Customizable plugin system to fetch videos from *any* website.
2.  **🎬 Process**: Automatically generates and merges a professional **Title Card (Intro)** with your video.
3.  **📤 Upload**: Smartly chooses between **User Account** (for huge files >50MB) and **Bot API** (for small files) to bypass limitations.

---

## ✨ Key Features

*   **🧩 Modular Scraper Architecture**: Comes with a template `SiteScraper` class. Just implement the link extraction logic for your target site.
*   **🧠 Smart Title Extraction**:
    *   Reads video metadata first.
    *   Fallbacks to intelligent filename parsing (e.g., converts `005_advanced_python.mp4` -> `Advanced Python`).
*   **🎨 Pro-Grade Intros**:
    *   Generates a 5-second Title Card using `Pillow` and `FFmpeg`.
    *   Full support for **RTL (Persian/Arabic) Text** handling via `Arabic-Reshaper` and `Python-Bidi`.
*   **🛡️ Robust Upload Engine**:
    *   **Resume Capability**: Never re-processes existing videos.
    *   **Hybrid Uploading**: Automatically switches to "User Mode" (Pyrogram) for large files to avoid Bot API limits.
    *   **Peer Auto-Discovery**: Automatically scans your dialog history to resolve Channel IDs and prevent `PEER_ID_INVALID` errors.
*   **📊 History Analysis**: Includes tools to scan your channel and report missing video numbers.

---

## 📂 Project Structure

```bash
telegram-video-automation/
├── downloads/                  # 📥 Raw downloaded videos go here
├── processed/                  # 📤 Videos with intro added (ready for upload)
├── scripts/                    # 🛠️ Executable scripts
│   ├── run_scraper.py          # Step 1: Download videos
│   ├── auth_login.py           # Step 2: Login to Telegram (User Account)
│   ├── process_and_upload.py   # Step 3: Add Intro & Upload (The Main Script)
│   ├── diagnose_channel.py     # Utilities: Find Channel IDs
│   └── check_channel_history.py# Utilities: Check for missing videos
├── src/                        # 🧠 Core Source Code
│   ├── scrapers/               # scraper plugins
│   ├── video_utils.py          # Intro generation & FFmpeg logic
│   └── telegram_utils.py       # Telegram upload wrapper
└── .env                        # 🔑 Configuration (API Keys)
```

---

## 🚀 Installation

### 1. Prerequisites
*   **Python 3.10** or higher.
*   **FFmpeg**: Must be installed and accessible in your system PATH.
    *   *Mac*: `brew install ffmpeg`
    *   *Linux*: `apt install ffmpeg`
    *   *Windows*: Download binary and add to PATH.

### 2. Clone & Install
```bash
git clone https://github.com/your-username/telegram-video-automation.git
cd telegram-video-automation
pip install -r requirements.txt
```

### 3. Configuration
Create a `.env` file in the root directory:

```ini
# --- Telegram API Credentials ---
# Get these from https://my.telegram.org
API_ID=12345678
API_HASH=your_api_hash_here

# --- Target Channel ---
# Can be a Username (@channel) or ID (-100...)
# Recommendation: Use ID for private channels.
CHANNEL_ID=-1001234567890

# --- Optional: Bot Mode ---
# If you want to use a Bot for small files
TELEGRAM_TOKEN=123456:ABC-DEF...
```

---

## 🕹️ Usage Guide

### Step 1: Customize Scraper (Optional)
If you already have local videos, skip to Step 2.
To download videos, edit `src/scrapers/site_scraper.py`. Implement the `get_video_links()` method to return a list of video objects.
Then run:
```bash
python scripts/run_scraper.py
```

### Step 2: Authenticate (One-Time)
To allow the script to upload as **YOU** (not a bot), login once:
```bash
python scripts/auth_login.py
```
*Follow the on-screen prompts to verify your phone number.*

### Step 3: Run the Pipeline 🚀
Start the magic. This command will:
1.  Look for videos in `downloads/`.
2.  Generate title cards for them.
3.  Upload them to your configured Channel.

```bash
python scripts/process_and_upload.py
```
*Tip: This script is safe to restart. It skips already processed files.*

---

## 🛠️ Advanced Tools

### 🔍 Find Channel ID
Not sure what your Channel ID is? Or getting `Peer id invalid` errors?
Run the diagnostic tool:
```bash
python scripts/diagnose_channel.py
```
*It will scan your dialogs and even check "Saved Messages" for forwarded posts to find the real ID.*

### 📉 Check Missing Videos
Want to know if you missed any episode number in your channel sequence?
```bash
python scripts/check_channel_history.py
```

---

## 🎨 Customization

### Changing the Intro Font
Replace `assets/fonts/Vazir-Bold.ttf` with any TrueType font you like.
To use a different font file name, update `src/video_utils.py` constant `FONT_PATH`.

### Changing Intro Style
The logic for the title card (background color, text color, size) is in `src/video_utils.py` -> `create_intro_image`. You can customize the Pillow drawing calls there.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome!

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

## ⚖️ License
Distributed under the MIT License. See `LICENSE` for more information.
