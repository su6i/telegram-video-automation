# Copilot / AI Agent Instructions

Purpose: Help an AI coding agent become productive in this repo quickly — architecture, workflows, conventions, and concrete examples.

1) Big picture
- Pipeline: `scrapers` -> `downloads/` (or custom paths) -> `processed/` -> upload to Telegram.
- Key code: `src/scrapers/` (site plugins), `src/video_utils.py` (intro, splitting, ffmpeg), `src/telegram_utils.py` (upload logic), `scripts/process_and_upload.py` (orchestration).
- Storage: `.storage/` holds generated manifests, upload history, and config (gitignored).
- Media paths: `src/media_resolver.py` handles multiple video directories (external drives, etc.).

2) Core workflows (copy/paste)
- Setup: `pip install -r requirements.txt` (Python 3.10+; `ffmpeg` must be on PATH).
- Login: `./run_auth.sh` or `python scripts/auth_login.py` (creates Pyrogram session files like `hybrid_account.session`).
- Scan -> Download: `./scan.sh` then `./download.sh` (produces `downloaded_video.txt` in `.storage/`).
- Archive pages: `python scripts/scan_and_archive_pages.py` (saves all course pages with images/links to `.storage/page_archives/`).
- Process & Upload: `python scripts/process_and_upload.py --intro` (auto-updates manifest with ✅ UPLOADED status).
- Check status: `python scripts/check_upload_status.py` (shows pending/uploaded/failed count).
- Utilities: `python scripts/check_channel_history.py`, `./update_index.sh`.

3) Important, project-specific conventions
- **Manifest & Storage**: All generated files live in `.storage/`:
  - `downloaded_video.txt` — **unified manifest** with 4 columns: `INDEX | TITLE | URL | STATUS`
    - Status: `✅ UPLOADED (msg_id: 12345)` | `⏳ PROCESSING` | `❌ FAILED` | (empty = pending)
  - `upload_history.json` — legacy backup of upload records
  - `failed_downloads.txt` — failed download attempts
  - `scraped_content.json` — extra metadata (descriptions, links)
  - `media_paths.json` — config file listing all media directories
  - `page_archives/` — archived web pages with all assets (images, HTML, links)
- **Multi-drive support**: Videos can be spread across multiple external drives. Edit `.storage/media_paths.json` to add paths:
  ```json
  {
    "paths": [
      "downloads",
      "/Volumes/ExternalDrive1",
      "/Volumes/ExternalDrive2"
    ]
  }
  ```
  Script recursively scans all subdirectories. Use `src/media_resolver.list_all_videos()` to find videos.
- **Page Archiving**: `python scripts/scan_and_archive_pages.py` archives all course pages locally with images, links, metadata in `.storage/page_archives/`. Each page folder has: `index.html` (original), `metadata.json` (extracted links + images), `images/` (downloaded assets).
- Filenames: many scripts expect a 3-digit numeric index prefix (e.g., `001_Title.mp4`). Use `get_smart_title()` in `src/video_utils.py` to match project title logic.
- Intro font & path: default font used is `src/fonts/Vazir-Bold.ttf`; change `FONT_PATH`/font reference inside `src/video_utils.py` to update visuals.
- Upload thresholds and decision points: constants live in `src/video_utils.py` and `src/telegram_utils.py` (`SIZE_THRESHOLD_MB`, `BOT_MAX_SIZE_MB`, `USER_MAX_SIZE_MB`). Do not change semantics without updating callers.
- Async vs sync: upload helper functions are `async` (Pyrogram and Bot wrappers). Many orchestration scripts call `asyncio.run(...)` — preserve async signatures when editing.

4) Integration points & external deps
- Requires `ffmpeg` and `ffprobe` (used extensively by `src/video_utils.py`).
- Uses `yt-dlp` for scraping/downloading via `scripts/` helpers.
- Telegram: supports both Bot API and User Account (Pyrogram). Credentials live in `.env`: `API_ID`, `API_HASH`, `TELEGRAM_TOKEN`, `CHANNEL_ID`, `CHANNEL_USERNAME`.
- Session files: run flows create session files in repo root (e.g., `hybrid_account.session`, `index_bot.session`) — treat as secrets.

5) Tests & debugging
- Run unit tests: `pytest -q` (there are a few tests under `tests/`).
- Useful artifacts: Check `.storage/` for `failed_downloads.txt`, `upload_history.json`, `scraped_content.json` — check these when diagnosing runs.
- Media path issues: If videos aren't found, verify `.storage/media_paths.json` exists and paths are correct (test with `python -c "from src.media_resolver import list_all_videos; print(list_all_videos())"`).
- If ffmpeg fails, inspect subprocess stderr printed by `video_utils` (functions use `subprocess.run(..., capture_output=True)` and log tail of stderr).

6) Code-change guidance for AI agents
- When modifying video processing, update both `process_video_for_bot_safe` and `process_video_for_user_safe` to keep behavior consistent.
- Preserve environment keys and CLI flags (`--intro`, `--video-dir`).
- Maintain manifest parsing compatibility: `load_video_metadata()` in `scripts/process_and_upload.py` expects the manifest structure above.
- Keep upload signatures: `upload_with_bot(video_path, caption, token, channel_id)` and `upload_with_user_account(app, video_path, caption, channel_username)` are awaited and return message objects.

7) Quick examples to include in PRs
- Small edit: change intro font path in `src/video_utils.py` and run `./upload_to_telegram.sh --intro --video-dir downloads` locally.
- Add a new scraper plugin: copy `src/scrapers/site_scraper.py` template, implement `extract_links()` and register it in `scripts/scraper.py`.

If anything here is unclear or you'd like more examples (manifest parsing, ffmpeg commands, or upload error handling), tell me which area to expand.
