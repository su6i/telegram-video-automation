# Scan & Resume Guide

## Core Logic

The scanning engine is designed for efficiency and safety. It creates a "snapshot" of the remote site's structure without redundant scraping.

### Features
✅ **Incremental Scanning**: Compares remote lesson IDs with the local manifest entries. Only new lessons are parsed and appended.
✅ **Full Trace**: Every lesson is attributed to a specific module (Section) and course, maintaining the original hierarchy.
✅ **Safe Metadata**: Downloads and caches HTML source for lesson pages for offline processing of resources.

---

## Detailed Operation

### 1. Initial Scan
Builds the complete library manifest for the first time.
```bash
./scan.sh
```

### 2. New Content Discovery
Run this whenever you want to check for new course updates.
```bash
./scan.sh --scan
```
- **Scenario**: You had 85 videos, 5 new ones were released.
- **Output**: 
  ```
  📋 Found 85 existing videos in manifest
  ✅ Found 5 NEW videos (85 + 5 = 90 total).
  ```

### 3. Verification & Testing
Target a specific amount of content for debugging purposes.
```bash
./scan.sh --limit 5
```

---

## Execution Pipeline

After scanning, the subsequent steps are:

1. **Download**: `bash download.sh` fetches the physical media.
2. **Process & Upload**: `python3 scripts/process_and_upload.py` encodes and distributes to Telegram.

---

**Note**: All scan status and logs are kept in the `.storage/` directory. If you manually edit the manifest file, ensure you maintain the pipe-delimited (`|`) format to avoid parsing errors.
