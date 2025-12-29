# 🔍 Scan & Resume Guide

**Navigation:** [README](README.md) | [Quick Start](QUICK_START.md) | [Scan & Resume](SCAN_RESUME.md)

---

## 🛠️ Manifest Discovery

Scanning is the first layer of the pipeline. It builds the `downloaded_video.txt` manifest which acts as the "Source of Truth" for all subsequent download and upload phases.

### 🔄 Incremental Operations
- **Full Scan**: Run `./scan.sh` to extract the complete hierarchy.
- **Deep Resume**: If the process is interrupted, re-running `./scan.sh` will verify existing entries and only scrape missing content.

## 💾 Local Storage
All scan results are cached in the `.storage/` directory to prevent redundant network requests:
- `downloaded_video.txt`: Flat list of all discovered lessons.
- `scraped_content.json`: Detailed descriptions and associated resource links.
- `page_archives/`: Cached HTML source for offline processing.

---

**Next Steps:** Proceed to the [Download Phase](QUICK_START.md).
