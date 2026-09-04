#!/usr/bin/env python3
"""Republish the bottom index at the end of the channel."""
import argparse
import asyncio
import json
import os
import pathlib
import sys

from dotenv import load_dotenv

# The repo root has to be on sys.path before anything under src/ is imported —
# running this file as a script puts tools/channel/ on sys.path, not the root.
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.env_resolver import env_path

load_dotenv(env_path())

from pyrogram import Client
from pyrogram.errors import FloodWait

from src.index_builder import (
    UNBOUNDED,
    build_index_or_fail,
    read_manifest,
    utf16_len,
    visible,
)

DEFAULT_STATE_IDS = [685, 686, 687, 688, 689, 690, 691]
# These 7 ids are the legacy fixed bottom-index slots. They must NEVER be
# passed to delete_messages by this tool: the owner's decision (T-943) is to
# repurpose them (see tools/channel/remodel_head.py's POST_LIBRARY_SLOTS),
# not delete them -- a deleted message can never be edited again.
PROTECTED_FROM_DELETE = frozenset(DEFAULT_STATE_IDS)

TEXT_LIMIT = 4096
ENT_LIMIT = 100  # mirror src/index_builder.ENT_LIMIT for the dry-run report


def state_file_path(data_dir) -> pathlib.Path:
    return data_dir / "bottom_index_state.json"


def load_state(path) -> dict:
    """Seed {"ids": DEFAULT_STATE_IDS, "pinned": None} on first run (file
    missing) so the first republish retires 685-691 correctly."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ids": list(DEFAULT_STATE_IDS), "pinned": None}


def save_state(path, ids, pinned) -> None:
    path.write_text(json.dumps({"ids": ids, "pinned": pinned}, indent=2), encoding="utf-8")


def build_bottom_index_posts(entries, msg_of, internal, attach_state):
    """Full parity with the head index, no slot ceiling."""
    return build_index_or_fail(
        entries, msg_of, internal, attach_state, UNBOUNDED,
        "publish_bottom_index.py", include_resource=True, include_subtitle=True,
    )


def post_report(posts) -> list[dict]:
    """One dict per post for the dry-run report: index, utf16 chars, entities.
    Entity count uses the same formula tests/test_index_builder.py already
    uses: post.count('<a ') + post.count('<b>')."""
    out = []
    for i, body in enumerate(posts, 1):
        out.append({
            "post": i,
            "chars": utf16_len(visible(body)),
            "entities": body.count("<a ") + body.count("<b>"),
        })
    return out


def ids_to_delete(old_ids) -> list:
    """Old ids minus anything protected (see PROTECTED_FROM_DELETE)."""
    return [i for i in old_ids if i not in PROTECTED_FROM_DELETE]


async def post_new_index(app, chat_id, posts) -> list:
    """Send every new post BEFORE anything is deleted. disable_notification
    is always True -- without it every republish fires one notification per
    post at every member. Retries on FloodWait; any other exception
    propagates immediately and nothing has been deleted at that point."""
    new_ids = []
    for body in posts:
        while True:
            try:
                msg = await app.send_message(
                    chat_id, body,
                    disable_notification=True,
                    disable_web_page_preview=True,
                )
                new_ids.append(msg.id)
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
    return new_ids


async def delete_old_index(app, chat_id, ids) -> None:
    """Only ever called after post_new_index has returned successfully.
    No-op (no client call at all) when `ids` is empty -- this is how
    PROTECTED_FROM_DELETE ids are skipped on the first run."""
    if not ids:
        return
    while True:
        try:
            await app.delete_messages(chat_id, ids)
            return
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)


async def move_pin(app, chat_id, new_first_id, old_pinned_id) -> None:
    """Only ever called after delete_old_index has returned successfully."""
    await app.pin_chat_message(chat_id, new_first_id, disable_notification=True)
    if old_pinned_id is not None:
        await app.unpin_chat_message(chat_id, old_pinned_id)


async def republish_bottom_index(app, chat_id, posts, old_ids, old_pinned_id) -> list:
    """The whole ordered operation: post -> delete (protected ids filtered
    out) -> pin. Returns the new message ids. A failure in post_new_index
    propagates before delete/pin are ever called. A failure in
    delete_old_index propagates after all new posts exist but before the pin
    moves -- callers must not persist state (save_state) when this raises,
    so a re-run retries the delete against the same old ids."""
    new_ids = await post_new_index(app, chat_id, posts)
    await delete_old_index(app, chat_id, ids_to_delete(old_ids))
    await move_pin(app, chat_id, new_ids[0], old_pinned_id)
    return new_ids


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually edit; without it nothing is sent (owner-only)")
    ap.add_argument("--backup", default=None,
                    help="where to write the current state before changes")
    args = ap.parse_args()

    data = pathlib.Path(os.getenv(
        "TVA_DATA",
        "/Users/su6i/.local/share/agent-projects/telegram-video-automation/data"))
    chat_id = int(os.getenv("CHANNEL_ID"))
    internal = abs(chat_id) - 1000000000000

    mp = json.loads((data / "message_ids.json").read_text(encoding="utf-8"))
    attach_state = json.loads(
        (data / "attachments_state.json").read_text(encoding="utf-8"))
    msg_of = {k: (v if isinstance(v, int) else v.get("video")) for k, v in mp.items()}
    entries = read_manifest()

    posts = build_bottom_index_posts(entries, msg_of, internal, attach_state)
    state = load_state(state_file_path(data))

    report = post_report(posts)
    print(f"📋 index needs {len(posts)} posts:")
    for r in report:
        print(f"   post {r['post']}: {r['chars']} chars, {r['entities']} entities")
    print(f"📋 would retire {len(state['ids'])} old ids: {state['ids']}")
    
    to_delete = ids_to_delete(state['ids'])
    protected = [i for i in state['ids'] if i in PROTECTED_FROM_DELETE]
    if protected:
        print(f"   (protected {len(protected)}: {protected})")
    print(f"   -> {len(to_delete)} to actually delete: {to_delete}")

    for i, body in enumerate(posts, 1):
        if utf16_len(visible(body)) > TEXT_LIMIT or (body.count("<a ") + body.count("<b>")) > ENT_LIMIT:
            raise SystemExit(f"❌ post {i} exceeds cap")

    if not args.apply:
        print("🛈 dry run — nothing was sent. Re-run with --apply.")
        return

    if args.backup:
        with open(args.backup, "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            json.dump(state, fh, ensure_ascii=False, indent=1)
        print(f"💾 backed up state -> {args.backup}")

    app = Client("hybrid_account", api_id=os.getenv("API_ID"),
                 api_hash=os.getenv("API_HASH"), workdir=str(REPO))
    async with app:
        new_ids = await republish_bottom_index(app, chat_id, posts, state["ids"], state["pinned"])
        save_state(state_file_path(data), new_ids, new_ids[0])
        print(f"✅ posted {len(new_ids)}, retired {len(state['ids'])} ({len(to_delete)} deleted), pin -> {new_ids[0]}")


if __name__ == "__main__":
    asyncio.run(main())
