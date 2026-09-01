#!/usr/bin/env python3
"""
Attach resources and subtitles to lesson videos in Telegram.

Deduplicates identical resource packs across lessons, zips unique packs into
size-capped parts, and attaches them as replies to the original video message.
Duplicate lessons get a text pointer to the canonical pack's message.

    uv run tools/knowledge/attach_resources.py \
        --resources /Volumes/Archive/_resources \
        --subtitles data/subtitles \
        --map data/message_ids.json \
        --state data/attachments_state.json \
        --dry-run

Resumable: sent parts are recorded in the state JSON. A failed upload can be
retried and will skip already-sent parts and already-built zips.
"""
import argparse
import asyncio
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from src.env_resolver import env_path as vault_env_path


def get_signature(lesson_dir):
    """Return sorted tuple of (rel_path_posix, size) for all files."""
    files = []
    for p in lesson_dir.rglob("*"):
        if p.is_file():
            if p.name == ".DS_Store" or p.name.startswith("._"):
                continue
            rel = p.relative_to(lesson_dir).as_posix()
            files.append((rel, p.stat().st_size))
    files.sort()
    return tuple(files)


def dedupe_resources(resources_dir):
    """Group lesson indexes by their exact file signature."""
    signatures = defaultdict(list)
    if resources_dir.exists():
        for p in resources_dir.iterdir():
            if p.is_dir() and re.match(r'^\d{3}$', p.name):
                sig = get_signature(p)
                signatures[sig].append(p.name)
            
    groups = {}
    for sig, idxs in signatures.items():
        idxs.sort()
        canonical = idxs[0]
        groups[canonical] = {
            "signature": sig,
            "duplicates": idxs[1:]
        }
    return groups


# Media and archives are already compressed; deflating them again costs
# minutes of CPU per gigabyte and saves nothing.
PRECOMPRESSED = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm",
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic",
    ".zip", ".gz", ".bz2", ".xz", ".7z", ".rar",
}


def compression_for(path):
    """Store already-compressed files, deflate the rest."""
    return zipfile.ZIP_STORED if path.suffix.lower() in PRECOMPRESSED else zipfile.ZIP_DEFLATED


def build_packs(args, groups, resources_dir):
    """Pack each canonical lesson's files into zip bins <= max_part_gb."""
    max_bytes = int(args.max_part_gb * 1024**3)
    parts_by_canonical = {}
    
    for canonical, data in groups.items():
        sig = data["signature"]
        # Sort by size DESC, rel_path ASC for bin packing
        files_for_packing = sorted(sig, key=lambda x: (-x[1], x[0]))
        
        bins = []
        for f in files_for_packing:
            rel, size = f
            placed = False
            for b in bins:
                if b['size'] + size <= max_bytes:
                    b['files'].append(f)
                    b['size'] += size
                    placed = True
                    break
            if not placed:
                bins.append({'size': size, 'files': [f]})
                
        parts_by_canonical[canonical] = bins
        
        print(f"📦 Lesson {canonical} pack plan: {len(bins)} part(s)")
        for i, b in enumerate(bins, 1):
            sz_mb = b['size'] / (1024**2)
            if b['size'] > max_bytes:
                print(f"   ⚠️ Part {i}: {len(b['files'])} file(s), {sz_mb:.1f} MB (exceeds {args.max_part_gb} GB cap!)")
            else:
                print(f"   Part {i}: {len(b['files'])} file(s), {sz_mb:.1f} MB")
            
            if args.go:
                packs_dir = resources_dir / "_packs"
                packs_dir.mkdir(parents=True, exist_ok=True)
                zip_path = packs_dir / f"{canonical}_part{i}.zip"
                # A run killed mid-zip leaves a truncated file. Trusting its
                # mere existence would upload a corrupt pack, so the skip is
                # gated on the central directory actually being there.
                if zip_path.exists() and zipfile.is_zipfile(zip_path):
                    print(f"   ⏭️  Skipping existing zip {zip_path.name}")
                else:
                    if zip_path.exists():
                        print(f"   ♻️  {zip_path.name} is truncated, rebuilding")
                    print(f"   🗜️ Zipping {zip_path.name} ...", flush=True)
                    tmp_path = zip_path.with_suffix(".zip.part")
                    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for rel, _ in b['files']:
                            src_file = resources_dir / canonical / rel
                            zf.write(src_file, arcname=rel,
                                     compress_type=compression_for(src_file))
                    # Only now does the final name exist, so an interrupted
                    # run can never leave one behind.
                    tmp_path.replace(zip_path)
                            
    return parts_by_canonical


def find_subtitles(subtitles_dir):
    """Find subtitles and return {lesson_idx: Path}."""
    out = {}
    if subtitles_dir.exists():
        for p in subtitles_dir.iterdir():
            if p.is_file() and p.name.endswith(".srt"):
                m = re.match(r'^(\d{3})_', p.name)
                if m:
                    out[m.group(1)] = p
    return out


def load_state(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


async def send_with_flood_retry(factory, attempts=6):
    """Run a send, waiting out Telegram's rate limit instead of failing on it.

    A few hundred sends in one run reliably trips FloodWait. Without this the
    caller recorded each one as a permanent error and moved on, so a long run
    silently lost most of its messages.
    """
    from pyrogram.errors import FloodWait
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except FloodWait as e:
            wait = int(getattr(e, "value", 30)) + 2
            print(f"   ⏳ rate limited, waiting {wait}s (attempt {attempt}/{attempts})", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"still rate limited after {attempts} waits")


async def run_passes(args, groups, map_data, state, subtitles_by_idx, parts_by_canonical, target_id, state_file):
    internal_chat_id = None
    if target_id and str(target_id).startswith("-100"):
        internal_chat_id = str(target_id)[4:]
    else:
        print("⚠️ CHANNEL_ID does not start with -100; duplicate links will be skipped.")

    peer = None
    if target_id:
        if str(target_id).startswith('-') or str(target_id).isdigit():
            peer = int(target_id)
        else:
            peer = target_id

    app = None
    if args.go:
        from pyrogram import Client
        api_id = os.getenv("API_ID")
        api_hash = os.getenv("API_HASH")
        if not api_id or not api_hash:
            print("❌ API Credentials missing in .env")
            return
        if not peer:
            print("❌ CHANNEL_ID missing in .env")
            return
            
        app = Client("hybrid_account", api_id=api_id, api_hash=api_hash, workdir=args.workdir)
        await app.start()

    successes = 0
    errors = 0

    def save():
        if args.go:
            save_state(state_file, state)

    try:
        print("\n=== Pass A: Canonical Lessons ===")
        for canonical in sorted(groups.keys()):
            if canonical not in map_data:
                continue
            
            reply_to = map_data[canonical]
            if canonical not in state:
                state[canonical] = {
                    "role": "canonical",
                    "canonical_index": canonical,
                    "pack_parts": {},
                    "duplicate_note": None,
                    "subtitle": None,
                    "errors": []
                }
            
            # Send packs
            bins = parts_by_canonical[canonical]
            for i, b in enumerate(bins, 1):
                part_str = str(i)
                if part_str not in state[canonical]["pack_parts"]:
                    zip_path = Path(args.resources).expanduser() / "_packs" / f"{canonical}_part{i}.zip"
                    caption = f"📎 Resources — lesson {canonical} (part {i}/{len(bins)})"
                    
                    if not args.go:
                        print(f"   [DRY] Would send {zip_path.name} to msg {reply_to}")
                    else:
                        try:
                            print(f"   📤 Sending {zip_path.name} to msg {reply_to}...", flush=True)
                            msg = await send_with_flood_retry(lambda: app.send_document(
                                    chat_id=peer,
                                    document=str(zip_path),
                                    reply_to_message_id=reply_to,
                                    caption=caption))
                            state[canonical]["pack_parts"][part_str] = msg.id
                            save()
                            print(f"   ✅ Sent part {i} -> id {msg.id}")
                            successes += 1
                            await asyncio.sleep(args.delay)
                        except Exception as e:
                            print(f"   ❌ Error sending part {i}: {e}")
                            state[canonical]["errors"].append(f"part {i}: {str(e)}")
                            save()
                            errors += 1
            
            # Send subtitle
            if canonical in subtitles_by_idx:
                if not state[canonical].get("subtitle"):
                    srt_path = subtitles_by_idx[canonical]
                    caption = f"📝 Subtitles — lesson {canonical}"
                    if not args.go:
                        print(f"   [DRY] Would send {srt_path.name} to msg {reply_to}")
                    else:
                        try:
                            print(f"   📤 Sending {srt_path.name} to msg {reply_to}...", flush=True)
                            msg = await send_with_flood_retry(lambda: app.send_document(
                                    chat_id=peer,
                                    document=str(srt_path),
                                    reply_to_message_id=reply_to,
                                    caption=caption))
                            state[canonical]["subtitle"] = msg.id
                            save()
                            print(f"   ✅ Sent subtitle -> id {msg.id}")
                            successes += 1
                            await asyncio.sleep(args.delay)
                        except Exception as e:
                            print(f"   ❌ Error sending subtitle: {e}")
                            state[canonical]["errors"].append(f"subtitle: {str(e)}")
                            save()
                            errors += 1

        print("\n=== Pass B: Duplicate Lessons ===")
        for canonical, data in groups.items():
            for dup in data["duplicates"]:
                if dup not in map_data:
                    continue
                
                reply_to = map_data[dup]
                if dup not in state:
                    state[dup] = {
                        "role": "duplicate",
                        "canonical_index": canonical,
                        "pack_parts": {},
                        "duplicate_note": None,
                        "subtitle": None,
                        "errors": []
                    }
                
                canon_state = state.get(canonical, {})
                pack_parts = canon_state.get("pack_parts", {})
                
                first_part_msg_id = None
                if pack_parts:
                    first_part_key = sorted(pack_parts.keys(), key=int)[0]
                    first_part_msg_id = pack_parts[first_part_key]
                
                if not state[dup].get("duplicate_note"):
                    if not first_part_msg_id:
                        print(f"   ⚠️ Skipping pack note for duplicate {dup} (canonical {canonical} parts not sent yet)")
                    else:
                        if not internal_chat_id:
                            text = f"📎 Resources for this lesson are identical to lesson {canonical}."
                        else:
                            link = f"https://t.me/c/{internal_chat_id}/{first_part_msg_id}"
                            text = f"📎 Resources for this lesson are identical to lesson {canonical}:\n{link}"
                        
                        if not args.go:
                            print(f"   [DRY] Would send note for {dup} to msg {reply_to}: {text.replace(chr(10), ' ')}")
                        else:
                            try:
                                print(f"   📤 Sending note for {dup} to msg {reply_to}...", flush=True)
                                msg = await send_with_flood_retry(lambda: app.send_message(
                                        chat_id=peer,
                                        text=text,
                                        reply_to_message_id=reply_to))
                                state[dup]["duplicate_note"] = msg.id
                                save()
                                print(f"   ✅ Sent note -> id {msg.id}")
                                successes += 1
                                await asyncio.sleep(args.delay)
                            except Exception as e:
                                print(f"   ❌ Error sending note for {dup}: {e}")
                                state[dup]["errors"].append(f"note: {str(e)}")
                                save()
                                errors += 1
                                
                if dup in subtitles_by_idx:
                    if not state[dup].get("subtitle"):
                        srt_path = subtitles_by_idx[dup]
                        caption = f"📝 Subtitles — lesson {dup}"
                        if not args.go:
                            print(f"   [DRY] Would send {srt_path.name} to msg {reply_to}")
                        else:
                            try:
                                print(f"   📤 Sending {srt_path.name} to msg {reply_to}...", flush=True)
                                msg = await send_with_flood_retry(lambda: app.send_document(
                                        chat_id=peer,
                                        document=str(srt_path),
                                        reply_to_message_id=reply_to,
                                        caption=caption))
                                state[dup]["subtitle"] = msg.id
                                save()
                                print(f"   ✅ Sent subtitle -> id {msg.id}")
                                successes += 1
                                await asyncio.sleep(args.delay)
                            except Exception as e:
                                print(f"   ❌ Error sending subtitle for {dup}: {e}")
                                state[dup]["errors"].append(f"subtitle: {str(e)}")
                                save()
                                errors += 1

        print("\n=== Pass C: Subtitle-only Lessons ===")
        # Pass A and B only visit lessons that have a resource pack. Most
        # lessons have a subtitle and no resources at all, and without this
        # pass their subtitle is never sent.
        covered = set(groups)
        for data in groups.values():
            covered.update(data["duplicates"])

        for idx in sorted(subtitles_by_idx):
            if idx in covered or idx not in map_data:
                continue

            reply_to = map_data[idx]
            if idx not in state:
                state[idx] = {
                    "role": "subtitle-only",
                    "canonical_index": None,
                    "pack_parts": {},
                    "duplicate_note": None,
                    "subtitle": None,
                    "errors": []
                }

            if state[idx].get("subtitle"):
                continue

            srt_path = subtitles_by_idx[idx]
            caption = f"📝 Subtitles — lesson {idx}"
            if not args.go:
                print(f"   [DRY] Would send {srt_path.name} to msg {reply_to}")
                continue
            try:
                print(f"   📤 Sending {srt_path.name} to msg {reply_to}...", flush=True)
                msg = await send_with_flood_retry(lambda: app.send_document(
                        chat_id=peer,
                        document=str(srt_path),
                        reply_to_message_id=reply_to,
                        caption=caption))
                state[idx]["subtitle"] = msg.id
                save()
                print(f"   ✅ Sent subtitle -> id {msg.id}")
                successes += 1
                await asyncio.sleep(args.delay)
            except Exception as e:
                print(f"   ❌ Error sending subtitle for {idx}: {e}")
                state[idx]["errors"].append(f"subtitle: {str(e)}")
                save()
                errors += 1

    finally:
        if app:
            await app.stop()
            
    if args.go:
        print(f"\n📊 Run complete: {successes} successful sends, {errors} errors")


def main():
    ap = argparse.ArgumentParser(description="Attach resources and subtitles to lesson videos in Telegram.")
    ap.add_argument("--resources", required=True, help="external drive root containing NNN/ lesson directories")
    ap.add_argument("--subtitles", required=True, help="directory of NNN_Title.srt files")
    ap.add_argument("--map", required=True, help="message_ids.json")
    ap.add_argument("--state", required=True, help="attachments_state.json")
    ap.add_argument("--max-part-gb", type=float, default=1.8, help="max size of one zip part, in GiB")
    ap.add_argument("--only", action="append", metavar="NNN",
                    help="restrict the run to these lesson indexes (repeatable) — "
                         "use it to try --go on a single lesson first")
    ap.add_argument("--delay", type=float, default=2.0,
                    help="seconds to pause after each send; the channel limit is per-minute")
    ap.add_argument("--env", default=str(vault_env_path()), help="path to .env file")
    ap.add_argument("--workdir", default=".", help="pyrogram workdir")
    
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Compute and print only (default)")
    group.add_argument("--go", action="store_true", help="Actually zip files and send to Telegram")
    
    args = ap.parse_args()
    args.dry_run = not args.go

    resources_dir = Path(os.path.expanduser(args.resources))
    subtitles_dir = Path(os.path.expanduser(args.subtitles))
    map_file = Path(os.path.expanduser(args.map))
    state_file = Path(os.path.expanduser(args.state))
    env_file = Path(os.path.expanduser(args.env))

    with open(map_file, "r", encoding="utf-8") as f:
        map_data = json.load(f)

    state = load_state(state_file)

    print("🔍 Scanning resources...", flush=True)
    groups = dedupe_resources(resources_dir)

    only = {i.strip() for i in args.only} if args.only else None
    if only:
        # A named duplicate needs its canonical too, otherwise there is no pack
        # for its pointer message to point at.
        keep = {c: d for c, d in groups.items()
                if c in only or only.intersection(d["duplicates"])}
        for c, d in keep.items():
            d["duplicates"] = [x for x in d["duplicates"] if x in only or c in only]
        groups = keep
        print(f"   --only {', '.join(sorted(only))} → {len(groups)} pack group(s)")

    print("\n📦 Building pack plans...", flush=True)
    parts_by_canonical = build_packs(args, groups, resources_dir)

    print("\n📝 Scanning subtitles...", flush=True)
    subtitles_by_idx = find_subtitles(subtitles_dir)
    if only:
        subtitles_by_idx = {k: v for k, v in subtitles_by_idx.items() if k in only}

    load_dotenv(env_file)
    target_id = os.getenv("CHANNEL_ID") or os.getenv("CHANNEL_USERNAME")

    asyncio.run(run_passes(args, groups, map_data, state, subtitles_by_idx, parts_by_canonical, target_id, state_file))

    # Report stats
    canonical_count = len(groups)
    parts_total = sum(len(bins) for bins in parts_by_canonical.values())
    dup_groups = {c: len(d["duplicates"]) for c, d in groups.items() if d["duplicates"]}
    matched_subs = sum(1 for idx in subtitles_by_idx if idx in map_data)
    total_subs = len(subtitles_by_idx)
    
    all_input_indexes = set()
    for c, d in groups.items():
        all_input_indexes.add(c)
        all_input_indexes.update(d["duplicates"])
    all_input_indexes.update(subtitles_by_idx.keys())
    
    missing_in_map = sorted(list(all_input_indexes - set(map_data.keys())))
    
    print("\n=== End-of-Run Report ===")
    print(f"Canonical packs: {canonical_count}")
    print(f"Total zip parts: {parts_total}")
    print(f"Duplicate groups: {len(dup_groups)}")
    for c, size in dup_groups.items():
        print(f"   - {c}: {size} duplicate(s)")
    print(f"Subtitles: {total_subs} found, {matched_subs} matched to a map entry")
    
    if missing_in_map:
        print(f"\n⚠️ Lessons present in files but missing in --map:")
        print(f"   {', '.join(missing_in_map)}")
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
