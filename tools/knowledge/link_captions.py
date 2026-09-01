#!/usr/bin/env python3
"""
Append a link to each lesson's attachment message onto the video's caption.

A Telegram channel only ever appends: a reply posted after the channel was
filled lands at the end of the history, no matter which message it quotes.
So the resources for lesson 080 sit hundreds of messages below lesson 080's
video. Editing the video's own caption is the one way to put the pointer
where the reader already is.

    uv run tools/knowledge/link_captions.py \
        --map <vault>/data/message_ids.json \
        --state <vault>/data/attachments_state.json \
        --out <vault>/data/caption_links_state.json \
        --dry-run

--dry-run is the default and opens no Telegram connection. --go edits real
messages in the channel; it is resumable and idempotent — a caption that
already carries the link is left alone, both from the local state file and
from the live caption itself, so a lost state file cannot double-append.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

from src.env_resolver import env_path as vault_env_path

# Telegram's caption limit, in characters of plain text.
CAPTION_LIMIT = 1024

RESOURCES_LABEL = "📎 Resources & subtitles"
SUBTITLES_LABEL = "📝 Subtitles"
# Fallback for a caption that is already near the limit.
RESOURCES_LABEL_SHORT = "📎 Resources"


def internal_chat_id(target_id):
    """The -100XXXX form a channel is addressed by, without the -100 prefix."""
    t = str(target_id or "")
    return t[4:] if t.startswith("-100") else None


def choose_target(entry):
    """Which attachment message a lesson's caption should point at.

    The resource pack comes first — it is the message the subtitle and the
    duplicate note are grouped with. Returns (message_id, label) or None.
    """
    if not entry:
        return None
    parts = entry.get("pack_parts") or {}
    if parts:
        first = sorted(parts, key=int)[0]
        return parts[first], RESOURCES_LABEL
    if entry.get("duplicate_note"):
        return entry["duplicate_note"], RESOURCES_LABEL
    if entry.get("subtitle"):
        return entry["subtitle"], SUBTITLES_LABEL
    return None


def plan_edits(state, map_data):
    """[(lesson, video_message_id, attachment_message_id, label)] to edit."""
    plan = []
    for idx in sorted(state):
        target = choose_target(state[idx])
        if not target:
            continue
        video_id = map_data.get(idx)
        if not video_id:
            continue
        msg_id, label = target
        plan.append((idx, video_id, msg_id, label))
    return plan


def link_line(internal, msg_id, label):
    url = f"https://t.me/c/{internal}/{msg_id}"
    return f'\n\n<a href="{url}">{label}</a>', f"\n\n{label}", url


def fit_caption(caption_html, caption_text, internal, msg_id, label):
    """Return (new_html, new_len) or None when even the short label overflows."""
    candidates = [label]
    if label == RESOURCES_LABEL:
        candidates.append(RESOURCES_LABEL_SHORT)
    for candidate in candidates:
        html_line, text_line, _ = link_line(internal, msg_id, candidate)
        if len(caption_text) + len(text_line) <= CAPTION_LIMIT:
            return caption_html + html_line, len(caption_text) + len(text_line)
    return None


async def run(args, plan, internal, done, out_file):
    from pyrogram import Client
    from pyrogram.enums import ParseMode
    from pyrogram.errors import FloodWait, MessageNotModified

    api_id, api_hash = os.getenv("API_ID"), os.getenv("API_HASH")
    target_id = os.getenv("CHANNEL_ID") or os.getenv("CHANNEL_USERNAME")
    if not api_id or not api_hash:
        print("❌ API_ID / API_HASH missing in .env")
        return 1
    peer = int(target_id) if str(target_id).lstrip("-").isdigit() else target_id

    edited = skipped = failed = 0
    app = Client("hybrid_account", api_id=api_id, api_hash=api_hash, workdir=args.workdir)

    def save():
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(done, indent=2, ensure_ascii=False), encoding="utf-8")

    async with app:
        for idx, video_id, msg_id, label in plan:
            try:
                msg = await app.get_messages(peer, video_id)
            except Exception as e:
                print(f"   ❌ {idx}: could not read message {video_id}: {e}")
                failed += 1
                continue

            if not msg or msg.empty or msg.caption is None:
                print(f"   ⚠️ {idx}: message {video_id} has no caption, skipped")
                skipped += 1
                continue

            # A caption that already points into this channel was linked on an
            # earlier run — the state file is a cache, not the authority.
            if f"t.me/c/{internal}/" in msg.caption.html:
                done[idx] = {"video": video_id, "target": msg_id, "status": "already-linked"}
                save()
                skipped += 1
                continue

            fitted = fit_caption(msg.caption.html, str(msg.caption), internal, msg_id, label)
            if not fitted:
                print(f"   ⚠️ {idx}: caption is {len(msg.caption)} chars, no room for the link")
                done[idx] = {"video": video_id, "target": msg_id, "status": "no-room"}
                save()
                skipped += 1
                continue

            new_html, new_len = fitted
            while True:
                try:
                    await app.edit_message_caption(
                        chat_id=peer, message_id=video_id,
                        caption=new_html, parse_mode=ParseMode.HTML)
                    done[idx] = {"video": video_id, "target": msg_id, "status": "linked"}
                    save()
                    edited += 1
                    print(f"   ✅ {idx}: caption -> msg {msg_id} ({new_len} chars)")
                    break
                except FloodWait as e:
                    print(f"   ⏳ flood wait {e.value}s ...", flush=True)
                    await asyncio.sleep(e.value + 1)
                except MessageNotModified:
                    done[idx] = {"video": video_id, "target": msg_id, "status": "already-linked"}
                    save()
                    skipped += 1
                    break
                except Exception as e:
                    print(f"   ❌ {idx}: edit failed: {e}")
                    done[idx] = {"video": video_id, "target": msg_id, "status": f"error: {e}"}
                    save()
                    failed += 1
                    break

            await asyncio.sleep(args.delay)

    print(f"\n📊 edited {edited} | skipped {skipped} | failed {failed}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--map", required=True, help="message_ids.json")
    ap.add_argument("--state", required=True, help="attachments_state.json")
    ap.add_argument("--out", required=True, help="caption_links_state.json")
    ap.add_argument("--only", action="append", metavar="NNN",
                    help="restrict the run to these lesson indexes (repeatable)")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="seconds between edits; the channel rate limit is per-minute")
    ap.add_argument("--env", default=str(vault_env_path()))
    ap.add_argument("--workdir", default=".")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="print the plan only (default)")
    g.add_argument("--go", action="store_true", help="actually edit the captions")
    args = ap.parse_args()

    map_data = json.loads(Path(os.path.expanduser(args.map)).read_text(encoding="utf-8"))
    state = json.loads(Path(os.path.expanduser(args.state)).read_text(encoding="utf-8"))
    out_file = Path(os.path.expanduser(args.out))
    done = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}

    load_dotenv(os.path.expanduser(args.env))
    internal = internal_chat_id(os.getenv("CHANNEL_ID"))
    if not internal:
        print("❌ CHANNEL_ID must be the -100... form to build message links")
        return 1

    plan = plan_edits(state, map_data)
    if args.only:
        only = {i.strip() for i in args.only}
        plan = [row for row in plan if row[0] in only]

    pending = [row for row in plan if done.get(row[0], {}).get("status") != "linked"]
    print(f"🔗 lessons with an attachment: {len(plan)} | already linked: {len(plan) - len(pending)}")

    if not args.go:
        for idx, video_id, msg_id, label in pending[:20]:
            print(f"   [DRY] {idx}: caption of msg {video_id} += \"{label}\" -> "
                  f"https://t.me/c/{internal}/{msg_id}")
        if len(pending) > 20:
            print(f"   ... and {len(pending) - 20} more")
        print(f"\n📊 would edit {len(pending)} caption(s) — pass --go to apply")
        return 0

    return asyncio.run(run(args, pending, internal, done, out_file))


if __name__ == "__main__":
    raise SystemExit(main())
