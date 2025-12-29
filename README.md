# Telegram Video Automation Kit 🚀

A robust automation system for scraping course content, processing videos for Telegram compatibility, and uploading with rich metadata.

## 🌟 Features

- **Multi-Level Scraping**: Extracts courses, sections, and lessons with full descriptions and resources.
- **Smart Processing**: Automatically compresses videos to 720p and normalizes audio/video (25fps, 44.1kHz) for perfect Playback.
- **Rich Captions**: Generates professional Telegram captions with bold headers, cleaned links, and un-fragmented text.
- **Intelligent Thumbnails**: Automatically extracts a representative frame (at 5s) to avoid black covers.
- **Hybrid Upload**: Supports both **Bot API** (for small files) and **User Accounts** (for large files up to 2GB).
- **Metadata Sync**: Keeps a local manifest for tracking upload status and ensuring data integrity.

## 🛠️ Project Structure

- `src/`: Core logic (Scrapers, Video Utils, Telegram API).
- `scripts/`: Operational tools for scanning, processing, and database maintenance.
- `.storage/`: Persistent data (Manifest, Scraped JSON, Upload History).
- `processed/`: Temporary directory for encoded videos before upload.

## 🚀 Quick Start

1. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in your Telegram API credentials and channel details.

2. **Scan Course**:
   ```bash
   bash scan.sh
   ```

3. **Process & Upload**:
   ```bash
   python3 scripts/process_and_upload.py
   ```

## ⚖️ Requirements

- Python 3.8+
- FFmpeg (installed and in PATH)
- Dependencies: `pip install -r requirements.txt`

---
*Developed for AI Content Creator Automation.*
