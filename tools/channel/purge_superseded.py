"""Deletes the superseded/duplicate video messages that remodel_head.py's Stage 1 only re-captions.

Those messages sit in id ranges 65-109 and 126-237 by default, each is an old/lower-quality
re-upload superseded by a live lesson elsewhere in the channel. This is Stage 2 of the
channel remodel: irreversible deletion, dry-run by default.
"""

import argparse
import asyncio
import json
import os
import pathlib
import sys

from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.errors import FloodWait

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path
from tools.channel.remodel_head import duplicate_title, read_manifest

load_dotenv(env_path())


def parse_dup_range(spec: str) -> list[int]:
    ranges = []
    for part in spec.split(","):
        a, b = part.split("-")
        ranges.append((int(a), int(b)))
    return [i for a, b in ranges for i in range(a, b + 1)]


def filter_video_candidates(messages) -> list:
    filtered = []
    for m in messages:
        if (
            m is not None
            and not getattr(m, "empty", False)
            and getattr(m, "video", None)
        ):
            filtered.append(m)
    return filtered


def write_backup(path: str, records: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)


def prepare_purge_plan(candidates, live_by_title, internal):
    """Pure function to decide what gets deleted and build the backup records."""
    backup_records = {}
    target_ids = []
    report_lines = []

    for m in candidates:
        cap = m.caption or ""
        matched_title = duplicate_title(cap, live_by_title)
        already_rewritten = f"t.me/c/{internal}/" in cap

        report_lines.append(
            f"🛈 {m.id}: {matched_title or 'unmatched'} (rewritten: {'yes' if already_rewritten else 'no'})"
        )

        backup_records[str(m.id)] = {"caption": cap, "matched_title": matched_title}
        target_ids.append(m.id)

    return target_ids, backup_records, report_lines


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete")
    ap.add_argument("--backup", default=None, help="write json backup before deleting")
    ap.add_argument(
        "--dup-range", default="65-109,126-237", help="ranges of superseded ids"
    )
    args = ap.parse_args()

    chat_id = int(os.getenv("CHANNEL_ID"))
    internal = abs(chat_id) - 1000000000000

    entries = read_manifest()
    live_by_title = {title for _, _, _, title in entries}

    dup_candidates = parse_dup_range(args.dup_range)

    app = Client(
        "hybrid_account",
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        workdir=str(REPO),
    )

    async with app:
        candidates = []
        for i in range(0, len(dup_candidates), 100):
            batch = dup_candidates[i : i + 100]
            messages = await app.get_messages(chat_id, batch)
            candidates.extend(filter_video_candidates(messages))

        target_ids, backup_records, report_lines = prepare_purge_plan(
            candidates, live_by_title, internal
        )

        for line in report_lines:
            print(line)

        print(f"{len(target_ids)} messages would be deleted.")

        if args.backup:
            try:
                write_backup(args.backup, backup_records)
                print(f"💾 backed up {len(backup_records)} messages -> {args.backup}")
            except Exception as e:  # noqa: BLE001
                raise SystemExit(f"❌ backup failed: {e}")

        if not args.apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply.")
            return

        done = 0
        failed = 0
        for i in range(0, len(target_ids), 100):
            batch = target_ids[i : i + 100]
            while True:
                try:
                    await app.delete_messages(chat_id, batch)
                    done += len(batch)
                    break
                except FloodWait as e:
                    print(f"   ⏳ FloodWait {e.value}s")
                    await asyncio.sleep(e.value + 2)
                except Exception as e:  # noqa: BLE001
                    print(f"   ❌ delete batch failed: {e}")
                    failed += len(batch)
                    break

        print(f"\n✅ deleted {done} message(s), failed {failed}.")


if __name__ == "__main__":
    asyncio.run(main())
