#!/usr/bin/env python
"""
Check video upload status from manifest.
"""
import argparse
import pathlib
import sys

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts tools/debug/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.manifest_tracker import (
    get_failed_videos,
    get_pending_videos,
    get_uploaded_videos,
)


def main():
    parser = argparse.ArgumentParser(description="Check video upload status from manifest.")
    parser.parse_args()
    print("=" * 70)
    print("📊 Video Upload Status Report")
    print("=" * 70)
    
    # Pending
    pending = get_pending_videos()
    print(f"\n⏳ Pending ({len(pending)} videos):")
    if pending:
        for v in pending[:10]:  # Show first 10
            print(f"  {v['index']} | {v['title'][:50]}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")
    else:
        print("  (none)")
    
    # Uploaded
    uploaded = get_uploaded_videos()
    print(f"\n✅ Uploaded ({len(uploaded)} videos):")
    if uploaded:
        for v in uploaded[:10]:
            msg_id = v['status'].split('msg_id: ')[-1].rstrip(')')
            print(f"  {v['index']} | {v['title'][:45]} | msg_id: {msg_id}")
        if len(uploaded) > 10:
            print(f"  ... and {len(uploaded) - 10} more")
    else:
        print("  (none)")
    
    # Failed
    failed = get_failed_videos()
    print(f"\n❌ Failed ({len(failed)} videos):")
    if failed:
        for v in failed[:10]:
            print(f"  {v['index']} | {v['title'][:50]}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")
    else:
        print("  (none)")
    
    # Summary
    total = len(pending) + len(uploaded) + len(failed)
    if total > 0:
        percent_uploaded = (len(uploaded) / total) * 100
        print(f"\n📈 Progress: {len(uploaded)}/{total} ({percent_uploaded:.1f}%)")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
