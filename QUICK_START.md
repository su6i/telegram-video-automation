# 📚 Quick Start Guide

## One Command for Everything (Automated Pipeline)

### ✅ Full Extraction (Scan + Download + Process):
The most efficient way to run the kit is through the provided shell scripts.

```bash
./download-everything.sh
```

This performs the following steps sequentially:
1. **Scans** the target platform and updates the local manifest (`.storage/downloaded_video.txt`).
2. **Downloads** all missing videos into the `downloads/` directory.
3. **Extracts** lesson descriptions and resource links into `.storage/scraped_content.json`.

---

## Technical Architecture

The system is designed with modularity to ensure stability across high-volume downloads.

```
Project/
├── downloads/
│   ├── Course_A/
│   │   ├── Module_1/
│   │   │   ├── 001_Lesson_Title.mp4
│   │   │   └── ...
│   │   └── ...
│   └── ...
│
└── .storage/
    ├── downloaded_video.txt          # Manifest (Source of truth for uploads)
    ├── scraped_content.json          # Lesson metadata, links, and descriptions
    ├── all_links.json                # Aggregate JSON of every resource link found
    ├── page_archives/                # Local HTML archives of lesson pages
    └── descriptions/                 # Prepared text descriptions for Telegram
```

---

## Pipeline Breakdown

### Phase 1: Scanning
Scans the site structure to find all lessons and their metadata.
```bash
./scan.sh
```

### Phase 2: Downloading
Fetches the actual video files into the structured local storage.
```bash
./download.sh
```

### Phase 3: Uploading
Optimizes and uploads files to Telegram based on the manifest.
```bash
python scripts/process_and_upload.py --res 720
```

---

## Maintenance & Cleanup

### Resetting Downloads
```bash
rm -rf downloads/             # Delete all video files
rm -rf .storage/page_archives/ # Delete HTML cache
rm .storage/downloaded_video.txt # Reset the scan manifest
```

---

**Questions?** Refer to the main README.md or the script source code for detailed logic.
