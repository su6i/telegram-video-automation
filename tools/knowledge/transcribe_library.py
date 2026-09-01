#!/usr/bin/env python3
"""
Transcribe a video library with mlx-whisper (Apple Silicon, local, no API cost).

The transcripts are the raw source material for skill distillation. They are
personal data — the output directory belongs in the vault, never in the repo
(rule 035).

    uv run --directory <repo> tools/knowledge/transcribe_library.py \
        --videos /path/to/library \
        --out ~/.local/share/agent-projects/<project>/data/transcripts

Resumable: a lesson whose transcript already exists is skipped, so the run can
be interrupted and restarted at any time. The model is loaded once for the
whole run, not once per file.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}


def video_files(root):
    for path in sorted(Path(root).rglob("*")):
        if path.suffix.lower() in VIDEO_SUFFIXES and not path.name.startswith("._"):
            yield path


def lesson_key(path):
    """001_Some Title_1080p_crf23.mp4 -> ('001', 'Some Title')."""
    stem = path.stem
    m = re.match(r"^(\d{3})_(.*)$", stem)
    if not m:
        return None, stem
    index, rest = m.groups()
    rest = re.sub(r"_\d+p_crf\d+$", "", rest)
    return index, rest


def extract_audio(video, wav_path):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", str(wav_path)],
        check=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, help="root of the video library")
    ap.add_argument("--out", required=True, help="transcript directory (in the vault)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, help="stop after N new transcripts (pilot runs)")
    ap.add_argument("--mem-limit-gb", type=float, default=6.0,
                    help="hard cap on MLX unified memory (0 = no cap)")
    ap.add_argument("--cache-limit-gb", type=float, default=1.0,
                    help="cap on the MLX free-buffer cache (0 = cache disabled)")
    args = ap.parse_args()

    out_dir = Path(os.path.expanduser(args.out))
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = []
    for video in video_files(args.videos):
        index, title = lesson_key(video)
        name = f"{index}_{title}" if index else title
        target = out_dir / f"{re.sub(r'[/:]', '_', name)}.json"
        if not target.exists():
            todo.append((video, index, title, target))

    print(f"📹 library: {args.videos}")
    print(f"📝 transcripts: {out_dir}")
    print(f"   pending: {len(todo)}")
    if args.limit:
        todo = todo[: args.limit]
        print(f"   limited to: {len(todo)}")
    if not todo:
        return 0

    # Imported here so --help works without the model stack installed.
    import mlx.core as mx
    import mlx_whisper

    # MLX hands freed buffers to a reuse cache that is unbounded by default, so
    # a long run climbs to tens of GB of unified memory and the machine starts
    # swapping. Cap the cache, cap total memory, and give the buffers back after
    # every lesson (see the mx.clear_cache() below).
    if args.cache_limit_gb >= 0:
        mx.set_cache_limit(int(args.cache_limit_gb * 2 ** 30))
    if args.mem_limit_gb > 0:
        mx.set_memory_limit(int(args.mem_limit_gb * 2 ** 30))
        print(f"   memory cap: {args.mem_limit_gb:.1f} GB | "
              f"cache cap: {args.cache_limit_gb:.1f} GB")

    started = time.time()
    audio_seconds = 0.0
    for n, (video, index, title, target) in enumerate(todo, 1):
        print(f"[{n}/{len(todo)}] {index or '---'} {title[:60]}", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            try:
                extract_audio(video, wav)
            except subprocess.CalledProcessError as exc:
                print(f"   ⚠️ audio extraction failed: {exc}")
                continue

            t0 = time.time()
            result = mlx_whisper.transcribe(
                str(wav), path_or_hf_repo=args.model, language="en", verbose=None
            )
            took = time.time() - t0

        duration = result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0
        audio_seconds += duration
        payload = {
            "index": index,
            "title": title,
            "source": str(video),
            "model": args.model,
            "duration_seconds": round(duration, 1),
            "text": result.get("text", "").strip(),
            "segments": [
                {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
                for s in result.get("segments", [])
            ],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        mx.clear_cache()
        speed = duration / took if took else 0
        peak = mx.get_peak_memory() / 2 ** 30
        print(f"   ✅ {duration/60:.1f} min audio in {took:.1f}s ({speed:.1f}x) "
              f"[peak {peak:.1f} GB] -> {target.name}")

    elapsed = time.time() - started
    print(f"\n📊 {len(todo)} lessons | {audio_seconds/3600:.1f} h audio | "
          f"{elapsed/60:.1f} min wall ({audio_seconds/elapsed if elapsed else 0:.1f}x realtime)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
