#!/usr/bin/env python3
"""
Map lesson index -> Telegram message id, for attaching resources as replies.

Personal data — the output lands in the vault, never in this repository
(rule 035).

    uv run --directory <repo> tools/knowledge/message_map.py \
        --source both --backup <vault>/data/backup_captions.json \
        --manifest .storage/downloaded_video.txt \
        --out <vault>/data/message_ids.json

--source backup reads <vault>/data/backup_captions.json (offline, no network).
--source scan connects to Telegram with the existing pyrogram user session
and reads the real channel history (only run this when you actually want to
hit the network). --source both (default) tries backup first, then scan.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
from pyrogram import Client

from src.caption_index import extract_index_and_title
from src.env_resolver import env_path as vault_env_path


def load_backup(path):
    if not os.path.exists(path):
        print(f"❌ Backup file not found: {path}")
        sys.exit(1)
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to read backup JSON: {e}")
        sys.exit(1)
        
    out = {}
    for item in data:
        num, _title = extract_index_and_title(item.get("caption") or "")
        if num is not None:
            idx = f"{num:03d}"
            if idx not in out:
                out[idx] = item.get("message_id")
    return out


async def scan_telegram(env_path, workdir):
    load_dotenv(env_path)
    
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    target_id = os.getenv("CHANNEL_ID") or os.getenv("CHANNEL_USERNAME")
    
    if not api_id or not api_hash:
        print("⚠️ API_ID or API_HASH missing in .env")
        return {}
        
    if not target_id:
        print("⚠️ CHANNEL_ID and CHANNEL_USERNAME missing in .env")
        return {}
        
    if str(target_id).startswith('-') or str(target_id).isdigit():
        peer = int(target_id)
    else:
        peer = target_id
        
    app = Client("hybrid_account", api_id=api_id, api_hash=api_hash, workdir=workdir)
    out = {}
    seen = matched = with_video = 0

    try:
        async with app:
            async for msg in app.get_chat_history(peer):
                seen += 1
                # Only a video message can BE a lesson. The index posts open
                # with their first entry ("001 - Welcome!"), so reading text
                # messages too mapped lesson 001 to the table of contents and
                # replied its attachments onto the wrong message.
                if not msg.video:
                    continue
                with_video += 1
                # The index sits at the start of the caption in the early
                # uploads and on the third header line ("**NNN - Title**") in
                # the later ones, so match it at the start of any line.
                num, _title = extract_index_and_title(msg.caption or "")
                if num is not None:
                    matched += 1
                    idx = f"{num:03d}"
                    if idx not in out:
                        out[idx] = msg.id
    except Exception as e:
        print(f"⚠️ scan failed: {e}")

    print(f"   scanned {seen} messages | {with_video} videos | "
          f"{matched} carried a lesson index | {len(out)} distinct lessons")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["backup", "scan", "both"], default="both")
    ap.add_argument("--backup", help="path to backup_captions.json "
                                    "(default: backup_captions.json next to --out)")
    ap.add_argument("--manifest", default=".storage/downloaded_video.txt")
    ap.add_argument("--out", required=True, help="where to write message_ids.json")
    ap.add_argument("--env", default=str(vault_env_path()))
    ap.add_argument("--workdir", default=".")
    
    args = ap.parse_args()
    if not args.backup:
        args.backup = str(Path(args.out).parent / "backup_captions.json")
    
    results = {}
    
    if args.source in ("backup", "both"):
        results.update(load_backup(args.backup))
        
    if args.source in ("scan", "both"):
        scan_data = asyncio.run(scan_telegram(args.env, args.workdir))
        results.update(scan_data)
        
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:
        print(f"❌ Failed to write output: {e}")
        sys.exit(1)
        
    manifest_indexes = set()
    if os.path.exists(args.manifest):
        with open(args.manifest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("##") or line.startswith("# ==="):
                    continue
                m = re.match(r'^(?:# \[DONE\] )?(\d{3})(?:_|\s*\|)', line)
                if m:
                    manifest_indexes.add(m.group(1))
                    
    mapped = set(results.keys()).intersection(manifest_indexes)
    missing = sorted(list(manifest_indexes - mapped))
    
    print(f"✅ Mapped {len(mapped)}/{len(manifest_indexes)} lessons")
    if missing:
        print(f"Missing: {', '.join(missing)}")
    else:
        print("Missing: (none)")
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
