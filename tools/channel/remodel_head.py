#!/usr/bin/env python3
"""Rebuild the head of the channel without deleting a single message.

Telegram cannot insert a message into history, but it can edit one forever.
Everything above the library is therefore treated as a fixed set of slots to be
re-purposed:

    2      banner        the channel's name, as block art
    3      about         what the channel is, and how to use it
    4-11   index         the full table of contents, one post per chunk
    111-125  divider     art + a signpost, in the middle of the old duplicates
    291-305  tail spare  reserved, immediately above the library
    685-691  post-library  signpost + 6 spare slots, repurposed from the old fixed bottom index (T-943)
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

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts tools/channel/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path

load_dotenv(env_path())

from pyrogram import Client
from pyrogram.errors import FloodWait, MessageNotModified

from src.index_builder import (
    ENT_LIMIT,
    build_index_or_fail,
    read_manifest,
    utf16_len,
    visible,
)

CAPTION_LIMIT = 1024

# --- slots ------------------------------------------------------------------
BANNER_SLOT = 2
ABOUT_SLOT = 3
# Every id below is a message that exists and can still be edited. Ids that
# were never used or have been deleted are NOT slots: Telegram cannot edit a
# deleted message, ever. Verified live 2026-09-03 over ids 1-305 (T-940):
# 12-64 and 238-290 are deleted end to end -- the "reclaim 12-64" growth path
# the docs used to promise does not exist and never will.
INDEX_SLOTS = (
    [4, 5, 6, 7, 8, 9, 10, 11]              # was [4,5,6,7]; absorbed HEAD_SPARE
    + [70, 84, 90, 93, 99, 101, 103, 107]   # T-940: reclaimed caption-overflow
)                                           # orphans; 12-64 in between are all
                                            # deleted, so in the channel view
                                            # these read as a direct
                                            # continuation of the index.
HEAD_SPARE = []                             # exhausted -- see build_plan()'s guard
DIVIDER_SLOTS = list(range(111, 126))
# T-940: the other 10 reclaimed orphans, below the divider and above the tail.
MID_SPARE = [133, 186, 211, 216, 224, 226, 230, 232, 235, 237]
TAIL_SPARE = list(range(291, 306))

# T-943: 685-691 used to be the bottom index's fixed slots; the bottom index
# is now republished at the tail instead (tools/channel/publish_bottom_index.py)
# and never deletes these -- they are repurposed as editable text slots
# immediately above the resource-document block (692+ are documents, which
# can never become editable text again once created).
POST_LIBRARY_SLOTS = [685, 686, 687, 688, 689, 690, 691]

POST_LIBRARY_SIGNPOST = """<pre>
📎 R E S O U R C E S   S T A R T   H E R E
</pre>
<b>Every lesson's resource archive and subtitle file lives below this
point.</b> The 📎 and CC links in the index above jump straight to them."""


def count_entities(text):
    return len(re.findall(r"<a |<b>|<i>|<pre>", text))

def resolve_content_body(item, msg_of, internal):
    body = item["body_html"]
    for link in item.get("links", []):
        text = link["text"]
        lesson = link["lesson"]
        mid = msg_of.get(lesson)
        if mid is None:
            raise SystemExit(f"remodel_head.py: content item {item['key']!r} links lesson {lesson!r} which has no message id")
        if text not in body:
            raise SystemExit(f"remodel_head.py: content item {item['key']!r} link text {text!r} not found in body_html")
        anchor = f'<a href="https://t.me/c/{internal}/{mid}">{text}</a>'
        body = body.replace(text, anchor, 1)
    return body

def render_content_post(item, msg_of, internal):
    body = resolve_content_body(item, msg_of, internal)
    text = f"<b>{html.escape(item['title'])}</b>\n\n{body}"
    ent = count_entities(text)
    if ent > ENT_LIMIT:
        raise SystemExit(f"remodel_head.py: content item {item['key']!r} needs {ent} entities, over the {ENT_LIMIT} cap")
    vis = utf16_len(visible(text))
    if vis > 4096:
        raise SystemExit(f"remodel_head.py: content item {item['key']!r} is {vis} UTF-16 units, over the 4096 cap")
    return text

def spare_pool_size(posts):
    # POST_LIBRARY_SLOTS[1:] joins the content queue as the last pool so they don't sit permanently empty while content backs up elsewhere
    return (len(INDEX_SLOTS[len(posts):]) + len(HEAD_SPARE) + 
            (len(DIVIDER_SLOTS) - len(DIVIDER_ART)) + len(MID_SPARE) + 
            (len(TAIL_SPARE) - 1) + (len(POST_LIBRARY_SLOTS) - 1))


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

<b>📎 Resources and CC subtitles</b> live further down the channel; the link at
the bottom of each video's caption jumps straight to them.

<b>🔖 The posts below the index are reserved.</b> They are kept empty on
purpose, so the index can grow without deleting anything. Please do not ask
for them to be removed.

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


# --- the plan ---------------------------------------------------------------
def build_plan(entries, msg_of, internal, dup_ids, live_by_title, attach_state, content_items=None):
    content_items = content_items or []
    content_iter = iter(content_items)

    def take(label, i, total):
        item = next(content_iter, None)
        return SPARE.format(label=label, i=i, total=total) if item is None else render_content_post(item, msg_of, internal)

    n, c = len(entries), len({e[0] for e in entries})
    
    extra_hint = (
        "There is no reserve left to absorb: HEAD_SPARE went into "
        "INDEX_SLOTS for the entity-aware split (T-937) and the 8 reclaimed "
        "orphans went in after the purge (T-940). Ids 12-64 and 238-290 are "
        "deleted, and a deleted message can never be edited — they are not a "
        "growth path. The only ways forward are MID_SPARE (10 slots, but they "
        "sit below the divider, so the index would no longer read as one "
        "block) or posting new messages below the library. Owner decision. "
        "See TODO.md."
    )
    posts = build_index_or_fail(
        entries, msg_of, internal, attach_state, len(INDEX_SLOTS),
        "remodel_head.py", extra_hint=extra_hint
    )

    plan = []
    plan.append((BANNER_SLOT, "text", BANNER.format(n=n, c=c)))
    plan.append((ABOUT_SLOT, "text", ABOUT.format(n=n, c=c, i=len(posts))))
    for slot, body in zip(INDEX_SLOTS, posts):
        plan.append((slot, "text", body))
    free = INDEX_SLOTS[len(posts):]
    for i, slot in enumerate(free, 1):
        plan.append((slot, "text", take("INDEX SPARE", i, len(free))))
    for i, slot in enumerate(HEAD_SPARE, 1):
        plan.append((slot, "text", take("HEAD SPARE", i, len(HEAD_SPARE))))
    for i, slot in enumerate(DIVIDER_SLOTS):
        art = DIVIDER_ART[i] if i < len(DIVIDER_ART) else None
        if art:
            plan.append((slot, "text", f"<pre>{art}</pre>"))
        else:
            j = i - len(DIVIDER_ART) + 1
            plan.append((slot, "text", take("SPARE", j, len(DIVIDER_SLOTS) - len(DIVIDER_ART))))
    for i, slot in enumerate(MID_SPARE, 1):
        plan.append((slot, "text", take("MID SPARE", i, len(MID_SPARE))))
    for i, slot in enumerate(TAIL_SPARE, 1):
        if slot == TAIL_SPARE[-1]:
            plan.append((slot, "text",
                         "<pre>▼ ▼ ▼   T H E   L I B R A R Y   ▼ ▼ ▼</pre>\n"
                         "<b>Lesson 001 starts in the next message.</b>"))
        else:
            plan.append((slot, "text", take("TAIL SPARE", i, len(TAIL_SPARE) - 1)))
    for i, slot in enumerate(POST_LIBRARY_SLOTS):
        if i == 0:
            plan.append((slot, "text", POST_LIBRARY_SIGNPOST))
        else:
            plan.append((slot, "text", take("POST-LIBRARY SPARE", i, len(POST_LIBRARY_SLOTS) - 1)))
    for mid, title in dup_ids.items():
        live = live_by_title.get(title)
        body = (ARCHIVED.format(link=f"https://t.me/c/{internal}/{live}")
                if live else ARCHIVED_PLAIN)
        plan.append((mid, "caption", body))
    return plan, posts


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

    mp = json.loads((data / "message_ids.json").read_text(encoding="utf-8"))
    attach_state = json.loads(
        (data / "attachments_state.json").read_text(encoding="utf-8"))
    
    content_path = data / "spare_content.json"
    if content_path.exists():
        content_items = json.loads(content_path.read_text(encoding="utf-8"))
    else:
        content_items = []
        print(f"⚠️  no spare content at {content_path}, all spare slots fall back to the placeholder")

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

        plan, posts = build_plan(entries, msg_of, internal, dup_ids, live_by_title, attach_state, content_items=content_items)

        touched = [mid for mid, _, _ in plan if mid not in backup]
        for i in range(0, len(touched), 100):
            for m in await app.get_messages(chat_id, touched[i:i + 100]):
                if m is not None and not getattr(m, "empty", False):
                    backup[m.id] = m.text or m.caption or ""

        if args.backup:
            with open(args.backup, "w", encoding="utf-8") as fh:
                json.dump(backup, fh, ensure_ascii=False, indent=1)
            print(f"💾 backed up {len(backup)} messages -> {args.backup}")

        if args.preview:
            with open(args.preview, "w") as fh:
                fh.writelines(f"\n{'=' * 70}\nMSG {mid}  [{kind}]  "
                             f"{len(visible(body))} visible chars\n{'-' * 70}\n{body}\n" for mid, kind, body in plan)
            print(f"👁  preview -> {args.preview}")

        over = [(mid, utf16_len(visible(b))) for mid, k, b in plan
                if utf16_len(visible(b)) > (CAPTION_LIMIT if k == "caption" else 4096)]
        if over:
            raise SystemExit(f"❌ {len(over)} message(s) exceed the limit: {over[:5]}")

        placed = min(len(content_items), spare_pool_size(posts))
        unfit = content_items[placed:]
        print(f"🗂 spare content: {placed}/{len(content_items)} item(s) placed in {spare_pool_size(posts)} pool slot(s)")
        if unfit:
            print(f"⚠️  {len(unfit)} content item(s) did not fit and were held back: {[u['key'] for u in unfit]}")

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
