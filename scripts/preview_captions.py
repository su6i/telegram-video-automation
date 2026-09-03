#!/usr/bin/env python3
"""
Render the captions for every manifest entry offline.

Same build_caption() the uploader calls, so what this prints is what Telegram
would receive — without touching Telegram. Run it before every upload batch.

    uv run --directory <repo> scripts/preview_captions.py --out captions.txt
    uv run --directory <repo> scripts/preview_captions.py --index 013
    uv run --directory <repo> scripts/preview_captions.py --check
"""
import argparse
import importlib.util
import os
import pathlib
import re
import sys

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts scripts/ on sys.path, not the root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.caption_builder import CAPTION_LIMIT, build_caption

_uploader = None


def _load_uploader():
    global _uploader
    if _uploader is not None:
        return _uploader

    original_cwd = os.getcwd()
    try:
        os.chdir(REPO_ROOT)

        _spec = importlib.util.spec_from_file_location(
            "_uploader", os.path.join(REPO_ROOT, "scripts", "process_and_upload.py")
        )

        # process_and_upload parses argv at import time; hide our own flags from it.
        _saved_argv = sys.argv
        sys.argv = [_saved_argv[0]]
        _uploader = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_uploader)
        sys.argv = _saved_argv
    finally:
        os.chdir(original_cwd)

    return _uploader


# Anything that must never reach a published caption.
LEAK_PATTERNS = [
    (r'MARKDOWN.{0,2}LINK.{0,2}PLACEHOLDER', "unrestored link placeholder"),
    (r'\x00', "raw sentinel"),
    (r'@@@', "unstripped header marker"),
    (r'(?m)^\s*[•·*\-]\s*$', "bullet with no text"),
    (r'(?m)^\s*[.,;:]\s*$', "orphan punctuation line"),
    (r'(?i)CLICK\s*HERE', "uncleaned 'CLICK HERE' label"),
]


def iter_videos():
    """(index, filename) for every manifest entry that has a physical file."""
    physical = {}
    for filename, _full in _uploader.list_all_videos():
        idx = _uploader.get_index_from_filename(filename)
        if idx.isdigit():
            physical[idx] = filename

    for m in _uploader.get_all_manifest_videos():
        idx = m['index']
        if idx in physical:
            yield idx, physical[idx]


def render(filename):
    meta = _uploader.load_video_metadata(filename)
    extra = _uploader.load_extra_content(meta['url']) if meta else None
    title = os.path.splitext(filename)[0]
    return build_caption(meta, extra, title)


def main():
    ap = argparse.ArgumentParser(description="Render Telegram captions offline")
    ap.add_argument("--index", help="render a single manifest index (e.g. 013)")
    ap.add_argument("--out", help="write the full report to this file")
    ap.add_argument("--check", action="store_true",
                    help="only report captions with leaks or over the limit; exit 1 if any")
    args = ap.parse_args()
    _load_uploader()

    report = []
    problems = []

    for idx, filename in iter_videos():
        if args.index and idx != args.index:
            continue

        caption, overflow = render(filename)

        found = [label for pat, label in LEAK_PATTERNS if re.search(pat, caption + "\n" + overflow)]
        if len(caption) > CAPTION_LIMIT:
            found.append(f"caption is {len(caption)} chars (limit {CAPTION_LIMIT})")
        if found:
            problems.append((idx, filename, found))

        report.append(
            f"{'='*72}\n"
            f"[{idx}] {filename}\n"
            f"caption: {len(caption)} chars | overflow: {len(overflow)} chars"
            f"{' | ⚠️ ' + '; '.join(found) if found else ''}\n"
            f"{'-'*72}\n{caption}\n"
            + (f"{'-'*20} overflow {'-'*20}\n{overflow}\n" if overflow else "")
        )

    text = "\n".join(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"📝 wrote {len(report)} captions to {args.out}")
    elif not args.check:
        print(text)

    print(f"\n📊 rendered: {len(report)} | with problems: {len(problems)}")
    for idx, filename, found in problems:
        print(f"   ⚠️ {idx}: {'; '.join(found)}")

    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
