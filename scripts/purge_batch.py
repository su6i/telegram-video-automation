#!/usr/bin/env python3
"""
Remove the messages one upload run put into the channel.

Only messages this run created are touched: the video messages recorded in
.storage/upload_history.json, the reserved index placeholders, and the
"Continued" overflow replies. Anything the channel held before the run — an
earlier batch, manual posts — is listed as KEEP and never deleted.

    uv run --directory <repo> scripts/purge_batch.py            # dry run
    uv run --directory <repo> scripts/purge_batch.py --apply
"""
import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from pyrogram import Client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)
os.chdir(ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
HISTORY = os.path.join(".storage", "upload_history.json")

PLACEHOLDER_MARK = "Index Reserved"
OVERFLOW_MARK = "Continued"


async def resolve(app):
    """Same contract as update_captions.resolve_channel: this id or nothing."""
    try:
        return await app.get_chat(CHANNEL_ID)
    except Exception as exc:
        print(f"⚠️ cold peer cache ({exc}); priming from dialogs...")
        async for d in app.get_dialogs():
            if d.chat.id == CHANNEL_ID:
                return await app.get_chat(CHANNEL_ID)
    raise SystemExit(f"❌ CHANNEL_ID {CHANNEL_ID} unreachable from this account.")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete")
    ap.add_argument("--lookback", type=int, default=40,
                    help="ids to scan before the first uploaded video (default 40)")
    args = ap.parse_args()

    with open(HISTORY, encoding="utf-8") as f:
        history = json.load(f)
    if not history:
        raise SystemExit("upload_history.json is empty — nothing from a run to purge.")

    video_ids = {entry["msg_id"] for entry in history.values() if entry.get("msg_id")}
    lo = min(video_ids) - args.lookback
    hi = max(video_ids) + args.lookback

    app = Client("hybrid_account", api_id=API_ID, api_hash=API_HASH, workdir=ROOT)
    await app.start()
    chat = await resolve(app)
    print(f"📡 channel: {chat.title} ({chat.id})")

    scanned = []
    ids = list(range(max(1, lo), hi + 1))
    for start in range(0, len(ids), 200):
        for msg in await app.get_messages(chat.id, ids[start:start + 200]):
            if not msg or msg.empty:
                continue
            scanned.append(msg)

    doomed = {}
    for msg in scanned:
        text = (msg.caption or msg.text or "")
        if msg.id in video_ids:
            doomed[msg.id] = "video from this run"
        elif PLACEHOLDER_MARK in text:
            doomed[msg.id] = "index placeholder"

    # An overflow message replies to its video, and part 2/2 replies to part
    # 1/2 — follow the chain so no orphan "Continued" is left behind.
    changed = True
    while changed:
        changed = False
        for msg in scanned:
            if msg.id in doomed:
                continue
            text = (msg.caption or msg.text or "")
            if OVERFLOW_MARK in text and msg.reply_to_message_id in doomed:
                doomed[msg.id] = "overflow reply"
                changed = True

    kept = [(m.id, (m.caption or m.text or "")[:60].replace("\n", " "))
            for m in scanned if m.id not in doomed]
    doomed = [(mid, why) for mid, why in doomed.items()]

    print(f"\n🗑️  delete {len(doomed)} message(s):")
    for mid, why in sorted(doomed):
        print(f"   {mid}: {why}")
    print(f"\n🛟 keep {len(kept)} pre-existing message(s):")
    for mid, preview in sorted(kept)[:10]:
        print(f"   {mid}: {preview}")
    if len(kept) > 10:
        print(f"   ... and {len(kept) - 10} more")

    if not args.apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply.")
    else:
        target = [mid for mid, _ in doomed]
        for start in range(0, len(target), 100):
            await app.delete_messages(chat.id, target[start:start + 100])
        print(f"\n✅ deleted {len(target)} message(s).")

        with open(HISTORY, "w", encoding="utf-8") as f:
            json.dump({}, f)
        print("✅ upload_history.json reset — the next run starts at 001.")

    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
