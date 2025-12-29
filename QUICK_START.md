# 📚 Quick Start Guide

**Navigation:** [README](README.md) | [Quick Start](QUICK_START.md) | [Scan & Resume](SCAN_RESUME.md)

---

## 🛠️ Installation

1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment:** Create a `.env` file with your credentials (API_ID, API_HASH, etc.).

## 🚀 The 3-Step Pipeline

The entire system is controlled via three primary shell scripts:

### Phase 1: Scan
```bash
./scan.sh
```
Initializes the course structure and manifest.

### Phase 2: Download
```bash
./download.sh
```
Fetches physical media files.

### Phase 3: Upload
```bash
./upload.sh --res 720 --intro
```
Handles re-encoding and delivery to Telegram.

---

**Note:** For troubleshooting or advanced parameters, refer to the [Main README](README.md).
