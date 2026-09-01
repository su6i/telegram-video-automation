#!/usr/bin/env python3
"""
Download the shared drive resources a lesson links to.

Lesson pages link to worksheets, templates and PDFs on Google Drive. This
fetches them per lesson so the archive is complete. Downloads land in the
vault, never in the repo (rule 035).

    uv run --directory <repo> tools/knowledge/fetch_resources.py \
        --out ~/.local/share/agent-projects/<project>/data/resources

Resumable: a lesson whose directory already holds files is skipped. Links that
are permission-restricted are recorded in failures.json instead of stopping the
run — most libraries have a few.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DRIVE_RE = re.compile(r'https?://(?:drive|docs)\.google\.com/\S+')

STORAGE = ".storage"
MANIFEST = os.path.join(STORAGE, "downloaded_video.txt")
CONTENT = "scraped_content.json"


def manifest_index_by_url(path):
    """{lesson url: index} from the manifest lines 'NNN_Title | URL'."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\d{3})_.*?\s\|\s(\S+)", line.strip())
        if m:
            out[m.group(2)] = m.group(1)
    return out


def lesson_links(content, index_by_url):
    """[(index, [urls])] — drive/docs links per lesson, in manifest order."""
    per_index = {}
    for key, val in content.items():
        idx = index_by_url.get(key) or index_by_url.get(val.get("video_url", ""))
        urls = []
        for link in (val.get("links") or []):
            url = link.get("url", "")
            if DRIVE_RE.match(url):
                urls.append(url)
        for url in DRIVE_RE.findall(val.get("description", "") or ""):
            urls.append(url)
        if not urls:
            continue
        bucket = per_index.setdefault(idx or "___", [])
        for url in urls:
            if url not in bucket:
                bucket.append(url)
    return sorted(per_index.items(), key=lambda kv: kv[0])


def dir_bytes(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def fetch(url, dest, timeout):
    """Download one link. Returns (ok, detail, seconds, bytes_added).

    gdown prints its progress bar to a pipe we only read at the end, so a big
    folder looks frozen while it downloads — the byte count in the caller's log
    line is what tells the two apart.
    """
    dest.mkdir(parents=True, exist_ok=True)
    folder = "/folders/" in url
    # Flags are kept to the ones every gdown release accepts; older builds
    # reject --fuzzy/--remaining-ok and fail the whole download.
    cmd = ["gdown", "--continue"]
    if folder:
        cmd += ["--folder"]
    cmd += ["-O", str(dest) if folder else str(dest) + "/", url]
    before, t0 = dir_bytes(dest), time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok, detail = proc.returncode == 0, (proc.stderr or proc.stdout)[-400:]
    except subprocess.TimeoutExpired:
        # A timeout used to escape and kill the whole run; the partial files
        # stay on disk and --continue picks them up on the next pass.
        ok, detail = False, f"timed out after {timeout}s"
    return ok, detail, time.time() - t0, dir_bytes(dest) - before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="resource directory (in the vault)")
    ap.add_argument("--content", default=CONTENT)
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--limit", type=int, help="stop after N lessons (pilot runs)")
    ap.add_argument("--timeout", type=int, default=7200,
                    help="seconds one link may take (folders can be several GB)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-run only the links recorded in failures.json. A lesson that "
                         "failed part-way already has files, so the normal run skips it; "
                         "gdown --continue resumes the partial download.")
    args = ap.parse_args()

    with open(args.content, encoding="utf-8") as f:
        content = json.load(f)

    groups = lesson_links(content, manifest_index_by_url(args.manifest))
    out_root = Path(os.path.expanduser(args.out))
    out_root.mkdir(parents=True, exist_ok=True)

    if args.retry_failed:
        failures_file = out_root / "failures.json"
        if not failures_file.exists():
            print(f"✅ nothing to retry — no {failures_file}")
            return 0
        previous = json.loads(failures_file.read_text(encoding="utf-8"))
        todo = [(idx, [f["url"] for f in entries]) for idx, entries in sorted(previous.items())]
        print(f"🔁 retrying {len(todo)} lesson(s) from failures.json")
    else:
        todo = [(idx, urls) for idx, urls in groups
                if not any((out_root / idx).glob("*")) ]
        print(f"📎 lessons with drive resources: {len(groups)} | pending: {len(todo)}")
    if args.limit:
        todo = todo[: args.limit]

    failures = {}
    for n, (idx, urls) in enumerate(todo, 1):
        dest = out_root / idx
        print(f"[{n}/{len(todo)}] lesson {idx}: {len(urls)} link(s)", flush=True)
        for url in urls:
            ok, detail, took, added = fetch(url, dest, args.timeout)
            size = f"{added / 2 ** 20:.0f} MB in {took / 60:.1f} min"
            if ok:
                print(f"   ✅ {url[:70]} ({size})", flush=True)
            else:
                print(f"   ⚠️ failed: {url[:70]} ({size}) — {detail[:120]}", flush=True)
                failures.setdefault(idx, []).append({"url": url, "detail": detail})
        if not any(dest.glob("*")):
            dest.rmdir()

    got = sum(1 for p in out_root.iterdir() if p.is_dir() and any(p.glob("*")))
    files = sum(1 for p in out_root.rglob("*") if p.is_file())
    print(f"\n📊 lessons with files: {got} | files: {files} | lessons with failures: {len(failures)}")
    failures_file = out_root / "failures.json"
    if failures:
        failures_file.write_text(
            json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"   details -> {failures_file}")
    elif args.retry_failed and failures_file.exists():
        failures_file.unlink()
        print(f"   every retried link succeeded -> removed {failures_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
