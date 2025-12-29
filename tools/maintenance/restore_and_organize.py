#!/usr/bin/env python3
"""
Quick script to restore the manifest from backup.
This prepares the file for re-scanning with the improved scraper.
"""

import os
import shutil

MANIFEST_FILE = ".storage/downloaded_video.txt"
BACKUP_FILE = "downloaded_video.pre_test_backup.txt"

if os.path.exists(MANIFEST_FILE):
    print(f"📋 Current manifest exists ({os.path.getsize(MANIFEST_FILE)} bytes)")
    print(f"   Backing up to: {MANIFEST_FILE}.corrupt_backup")
    shutil.copy(MANIFEST_FILE, f"{MANIFEST_FILE}.corrupt_backup")

if os.path.exists(BACKUP_FILE):
    print(f"📂 Found backup: {BACKUP_FILE}")
    print(f"   Restoring to: {MANIFEST_FILE}")
    shutil.copy(BACKUP_FILE, MANIFEST_FILE)
    print(f"✅ Restore complete! ({os.path.getsize(MANIFEST_FILE)} bytes)")
else:
    print(f"❌ Backup file not found: {BACKUP_FILE}")

print("\n💡 Next steps:")
print("   1. Run: python scripts/scraper.py --scan")
print("   2. The improved scraper will organize sections properly")
print("   3. Verify .storage/downloaded_video.txt has proper ## --- Section --- headers")
