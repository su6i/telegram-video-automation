#!/usr/bin/env python3
"""Rebuild the head of the channel without deleting a single message.

Telegram cannot insert a message into history, but it can edit one forever.
Everything above the library is therefore treated as a fixed set of slots to be
re-purposed:

    2      banner        the channel's name, as block art
    3      about         what the channel is, and how to use it
    4-7    index         the full table of contents, one post per chunk
    8-11   head spare    labelled, empty, reserved for index growth
    111-125  divider     art + a signpost, in the middle of the old duplicates
    291-305  tail spare  reserved, immediately above the library
    others   duplicates  old uploads: caption rewritten to point at the live
                         lesson; the video itself is left alone (stage 1 never
                         deletes)

The layout is data, not code: edit LAYOUT below when the channel grows.
"""
import argparse
import asyncio
import html
import json
import os
import pathlib
import re
import sys

from dotenv import load_dotenv

from src.env_resolver import env_path

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
load_dotenv(env_path())

from pyrogram import Client
from pyrogram.errors import FloodWait, MessageNotModified

LIMIT = 3700          # visible chars per index post; the hard cap is 4096
CAPTION_LIMIT = 1024

# --- slots ------------------------------------------------------------------
BANNER_SLOT = 2
ABOUT_SLOT = 3
INDEX_SLOTS = [4, 5, 6, 7]
HEAD_SPARE = [8, 9, 10, 11]
DIVIDER_SLOTS = list(range(111, 126))
TAIL_SPARE = list(range(291, 306))

BANNER = """<pre>
▄▀█ █
█▀█ █
█▀▀ █▀█ █▄░█ ▀█▀ █▀▀ █▄░█ ▀█▀
█▄▄ █▄█ █░▀█ ░█░ ██▄ █░▀█ ░█░
█▀▀ █▀█ █▀▀ ▄▀█ ▀█▀ █▀█ █▀█
█▄▄ █▀▄ ██▄ █▀█ ░█░ █▄█ █▀▄
</pre>
<b>{n} lessons · {c} courses · video + resources + subtitles</b>"""

ABOUT = """<pre>
╔══════════════════════════════╗
║  📚  H O W   T O   U S E     ║
╚══════════════════════════════╝
</pre>
<b>🎓 {c} full courses, {n} lessons, in order.</b>

<b>📑 The index</b> is the next {i} posts. Every lesson number in it is a link —
tap it and you land on that lesson's video.

<b>🎬 Each lesson</b> carries its description in the caption. Long descriptions
continue in the reply right underneath.

<b>📎 Resources and 📝 subtitles</b> live further down the channel; the link at
the bottom of each video's caption jumps straight to them.

<b>🔖 The posts above and below the index are reserved.</b> They are kept empty
on purpose, so a new lesson can be added to the index without deleting
anything. Please do not ask for them to be removed.

<i>📌 Pin: the first index post.</i>"""

SPARE = """<pre>
· · · · · · · · · · · · · · ·
      ▫ {label} ▫
· · · · · · · · · · · · · · ·
</pre>
<i>Reserved slot {i}/{total} — kept empty so the index can grow without
anything being deleted. Not a mistake, not spam.</i>"""

DIVIDER_ART = [
    "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░",
    "░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░",
    "░▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒░",
    "░▒▓███████████████████████▓▒░",
    "░▒▓█  A I   C O N T E N T █▓▒░",
    "░▒▓█    C R E A T O R     █▓▒░",
    "░▒▓███████████████████████▓▒░",
    "░▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒░",
    "░▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒░",
    "░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░",
]

ARCHIVED = ("🗄 <b>Superseded upload</b> — an earlier, lower-quality copy.\n"
            "The current version of this lesson is here: {link}")
ARCHIVED_PLAIN = ("🗄 <b>Superseded upload</b> — an earlier, lower-quality copy, "
                  "kept only so the message ids above the library stay stable.")


# --- the manifest -----------------------------------------------------------
def read_manifest():
    course = section = None
    out = []
    text = (REPO / ".storage/downloaded_video.txt").read_text()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# === "):
            course = line[6:].rsplit("===", 1)[0].strip()
            section = None
            continue
        if line.startswith("## --- "):
            section = line[7:].rsplit("---", 1)[0].strip()
            continue
        m = re.match(r"^(\d{3})_(.*?)\s*\|", line)
        if m:
            out.append((course, section, m.group(1), m.group(2).strip()))
    return out


def resource_and_subtitle_ids(entry):
    """(resource_msg_id_or_None, subtitle_msg_id_or_None) for one lesson."""
    if not entry:
        return None, None
    parts = entry.get("pack_parts") or {}
    resource_id = parts[sorted(parts, key=int)[0]] if parts else entry.get("duplicate_note")
    return resource_id, entry.get("subtitle")


def build_index(entries, msg_of, internal, attach_state):
    posts, lines, vis = [], [], 0
    cur_course = cur_section = None

    def close():
        nonlocal lines, vis
        if lines:
            posts.append("\n".join(lines))
            lines, vis = [], 0

    def add(h, v):
        nonlocal vis
        lines.append(h)
        vis += v + 1

    for c, s, num, title in entries:
        new_course, new_section = c != cur_course, s != cur_section
        cost = len(num) + 4 + len(title)
        cost += (len(c) + 5) if new_course else 0
        cost += (len(s) + 5) if new_section else 0
        if vis + cost > LIMIT and lines:
            close()
            cur_course, cur_section = c, s
            add(f"<b>🎓 {html.escape(c)} (continued)</b>", len(c) + 15)
            add("", 0)
            add(f"<b>📁 {html.escape(s)}</b>", len(s) + 3)
            new_course = new_section = False
        if new_course:
            if lines:
                add("", 0)
            cur_course, cur_section = c, None
            add(f"<b>🎓 {html.escape(c)}</b>", len(c) + 3)
            new_section = True
        if new_section:
            cur_section = s
            add("", 0)
            add(f"<b>📁 {html.escape(s)}</b>", len(s) + 3)
        mid = msg_of.get(num)
        resource_id, subtitle_id = resource_and_subtitle_ids(attach_state.get(num))
        extra = ""
        if resource_id:
            extra += f' <a href="https://t.me/c/{internal}/{resource_id}">📎</a>'
        if subtitle_id:
            extra += f' <a href="https://t.me/c/{internal}/{subtitle_id}">📝</a>'
        body = (f'<a href="https://t.me/c/{internal}/{mid}">{num}</a>{extra} · {html.escape(title)}'
                if mid else f"{num}{extra} · {html.escape(title)}")
        add(body, len(num) + 3 + len(title) + len(visible(extra)))
    close()
    return posts


def visible(s):
    return re.sub(r"<[^>]+>", "", s)


# --- the plan ---------------------------------------------------------------
def build_plan(entries, msg_of, internal, dup_ids, live_by_title, attach_state):
    n, c = len(entries), len({e[0] for e in entries})
    posts = build_index(entries, msg_of, internal, attach_state)
    if len(posts) > len(INDEX_SLOTS):
        raise SystemExit(
            f"index needs {len(posts)} posts but only {len(INDEX_SLOTS)} slots are "
            f"reserved — widen INDEX_SLOTS (take them from HEAD_SPARE) and re-run")

    plan = []
    plan.append((BANNER_SLOT, "text", BANNER.format(n=n, c=c)))
    plan.append((ABOUT_SLOT, "text", ABOUT.format(n=n, c=c, i=len(posts))))
    for slot, body in zip(INDEX_SLOTS, posts):
        plan.append((slot, "text", body))
    for slot in INDEX_SLOTS[len(posts):]:
        plan.append((slot, "text", SPARE.format(label="INDEX SPARE",
                                                i=slot, total="—")))
    for i, slot in enumerate(HEAD_SPARE, 1):
        plan.append((slot, "text", SPARE.format(label="HEAD SPARE",
                                                i=i, total=len(HEAD_SPARE))))
    for i, slot in enumerate(DIVIDER_SLOTS):
        art = DIVIDER_ART[i] if i < len(DIVIDER_ART) else None
        if art:
            plan.append((slot, "text", f"<pre>{art}</pre>"))
        else:
            j = i - len(DIVIDER_ART) + 1
            plan.append((slot, "text", SPARE.format(
                label="SPARE", i=j, total=len(DIVIDER_SLOTS) - len(DIVIDER_ART))))
    for i, slot in enumerate(TAIL_SPARE, 1):
        if slot == TAIL_SPARE[-1]:
            plan.append((slot, "text",
                         "<pre>▼ ▼ ▼   T H E   L I B R A R Y   ▼ ▼ ▼</pre>\n"
                         "<b>Lesson 001 starts in the next message.</b>"))
        else:
            plan.append((slot, "text", SPARE.format(label="TAIL SPARE", i=i,
                                                    total=len(TAIL_SPARE) - 1)))
    for mid, title in dup_ids.items():
        live = live_by_title.get(title)
        body = (ARCHIVED.format(link=f"https://t.me/c/{internal}/{live}")
                if live else ARCHIVED_PLAIN)
        plan.append((mid, "caption", body))
    return plan


def duplicate_title(caption, known):
    """Pull the lesson title out of an old duplicate's caption.

    Two caption shapes are in the channel and neither is trustworthy on its
    own: the older batch inlines course and section after the number
    ("001 - - Course Section 001 - Real Title") while the newer one puts them
    on their own lines. So every plausible title is generated and the one the
    manifest actually knows wins; an unmatched duplicate gets no link rather
    than a wrong one.
    """
    cands = []
    for line in caption.splitlines()[:4]:
        line = line.strip().lstrip("\u200e\u200f")
        # every "NNN - " position, not just the first: the older captions put
        # the real title after a second number further along the same line
        for m in re.finditer(r"\d{2,3}\s*-+\s*", line):
            tail = line[m.end():].strip()
            if tail:
                cands.append(tail)
        if line and not re.match(r"^\d", line):
            cands.append(line)
    for c in cands:
        if c in known:
            return c
    # the site's own punctuation drifts between the old upload and today's
    # manifest, so compare on a flattened key before giving up
    def key(x):
        return re.sub(r"[^a-z0-9]+", "", x.lower())

    flat = {key(k): k for k in known}
    for c in cands:
        hit = flat.get(key(c))
        if hit:
            return hit
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually edit; without it nothing is sent")
    ap.add_argument("--backup", default=None,
                    help="where to write the current content of every touched message")
    ap.add_argument("--preview", default=None, help="write the rendered plan here")
    ap.add_argument("--dup-range", default="65-109,126-237",
                    help="message id ranges holding the superseded uploads")
    args = ap.parse_args()

    data = pathlib.Path(os.getenv(
        "TVA_DATA",
        "/Users/su6i/.local/share/agent-projects/telegram-video-automation/data"))
    chat_id = int(os.getenv("CHANNEL_ID"))
    internal = abs(chat_id) - 1000000000000

    mp = json.load(open(data / "message_ids.json"))
    attach_state = json.load(open(data / "attachments_state.json"))
    msg_of = {k: (v if isinstance(v, int) else v.get("video")) for k, v in mp.items()}
    entries = read_manifest()
    live_by_title = {t: msg_of.get(num) for _, _, num, t in entries}

    ranges = []
    for part in args.dup_range.split(","):
        a, b = part.split("-")
        ranges.append((int(a), int(b)))
    dup_candidates = [i for a, b in ranges for i in range(a, b + 1)]

    app = Client("hybrid_account", api_id=os.getenv("API_ID"),
                 api_hash=os.getenv("API_HASH"), workdir=str(REPO))
    async with app:
        dup_ids, backup = {}, {}
        for i in range(0, len(dup_candidates), 100):
            for m in await app.get_messages(chat_id, dup_candidates[i:i + 100]):
                if m is None or getattr(m, "empty", False) or not m.video:
                    continue
                cap = m.caption or ""
                backup[m.id] = cap
                # Every duplicate is re-captioned, matched or not: leaving one
                # with its original caption makes it indistinguishable from the
                # live lesson, which is the confusion this pass exists to end.
                dup_ids[m.id] = duplicate_title(cap, set(live_by_title))

        plan = build_plan(entries, msg_of, internal, dup_ids, live_by_title, attach_state)

        touched = [mid for mid, _, _ in plan if mid not in backup]
        for i in range(0, len(touched), 100):
            for m in await app.get_messages(chat_id, touched[i:i + 100]):
                if m is not None and not getattr(m, "empty", False):
                    backup[m.id] = m.text or m.caption or ""

        if args.backup:
            json.dump(backup, open(args.backup, "w"), ensure_ascii=False, indent=1)
            print(f"💾 backed up {len(backup)} messages -> {args.backup}")

        if args.preview:
            with open(args.preview, "w") as fh:
                fh.writelines(f"\n{'=' * 70}\nMSG {mid}  [{kind}]  "
                             f"{len(visible(body))} visible chars\n{'-' * 70}\n{body}\n" for mid, kind, body in plan)
            print(f"👁  preview -> {args.preview}")

        over = [(mid, len(visible(b))) for mid, k, b in plan
                if len(visible(b)) > (CAPTION_LIMIT if k == "caption" else 4096)]
        if over:
            raise SystemExit(f"❌ {len(over)} message(s) exceed the limit: {over[:5]}")

        print(f"📋 plan: {len(plan)} edits "
              f"({sum(1 for _, k, _ in plan if k == 'text')} text, "
              f"{sum(1 for _, k, _ in plan if k == 'caption')} captions)")
        if not args.apply:
            print("🛈 dry run — nothing was sent. Re-run with --apply.")
            return

        done = skipped = failed = 0
        for mid, kind, body in plan:
            while True:
                try:
                    if kind == "text":
                        await app.edit_message_text(chat_id, mid, body,
                                                    disable_web_page_preview=True)
                    else:
                        await app.edit_message_caption(chat_id, mid, body)
                    done += 1
                    break
                except MessageNotModified:
                    skipped += 1
                    break
                except FloodWait as e:
                    print(f"   ⏳ FloodWait {e.value}s")
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    print(f"   ❌ {mid}: {e}")
                    failed += 1
                    break
        print(f"✅ edited {done}, unchanged {skipped}, failed {failed}")


if __name__ == "__main__":
    asyncio.run(main())
