#!/usr/bin/env python3
"""
Turn the JSON transcripts into .srt subtitle files, one per lesson.

    uv run --directory <repo> tools/knowledge/make_subtitles.py \
        --transcripts <vault>/data/transcripts --out <vault>/data/subtitles [--zip]
"""
import argparse
import json
import os
import sys
import zipfile
from pathlib import Path


def stamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments):
    lines = []
    for n, seg in enumerate(segments, 1):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(str(n))
        lines.append(f"{stamp(seg['start'])} --> {stamp(seg['end'])}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--zip", action="store_true", help="also write subtitles.zip next to --out")
    args = ap.parse_args()

    src = Path(os.path.expanduser(args.transcripts))
    dst = Path(os.path.expanduser(args.out))
    dst.mkdir(parents=True, exist_ok=True)

    written = 0
    for path in sorted(src.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        segments = data.get("segments") or []
        if not segments:
            continue
        target = dst / (path.stem + ".srt")
        target.write_text(to_srt(segments), encoding="utf-8")
        written += 1

    print(f"📝 subtitles written: {written} -> {dst}")

    if args.zip and written:
        archive = dst.parent / "subtitles.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for srt in sorted(dst.glob("*.srt")):
                z.write(srt, srt.name)
        print(f"🗜️  {archive} ({archive.stat().st_size/1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
