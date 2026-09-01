# The channel's layout

A Telegram channel is append-only: a message can never be inserted between two
existing ones. Every message above the library is therefore a **slot** — a fixed
address that can be edited forever but never moved. This document is the map of
those slots, and `tools/channel/remodel_head.py` is the only thing that writes
them.

## The map

| Slots | What lives there |
|---|---|
| `2` | Banner — the channel's name as block art, plus the lesson count |
| `3` | About — what the channel is and how to read it |
| `4`–`7` | The index. 283 lessons in 34 sections currently fill **4** posts |
| `8`–`11` | Head spare — labelled, deliberately empty |
| `65`–`109`, `126`–`237` | Superseded uploads from earlier runs. Stage 1 does **not** delete them; each caption is rewritten to say so and, where the title still matches the manifest, to link the live lesson |
| `111`–`125` | A divider: block art, then further spare slots |
| `291`–`305` | Tail spare, immediately above the library. The last one is the "library starts here" signpost |
| `306`+ | The library: 283 lessons, then their resources and subtitles |

## Sizing the index

Do not guess. One index line is a lesson number plus a title (~40 visible
characters); a section header adds ~30. Telegram allows 4096 visible characters
per text message and the tool packs to 3700, splitting a long section across
posts and repeating its header with `(continued)`.

Hyperlinks are free: Telegram counts entities separately, so linking every
lesson number to its video message costs nothing against the limit.

```
posts = ceil((lessons × 40 + sections × 30) / 3700)
```

At 283 lessons that is 4 posts, against 4 reserved index slots and 4 head
spares. **When the index needs a fifth post the tool refuses to run** and says
so — move a slot from `HEAD_SPARE` into `INDEX_SLOTS` and re-run. It will never
silently overwrite a video.

## Running it

Dry run first, always. It reads the live channel, renders every edit and writes
a backup of the current content, but sends nothing:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/remodel_head.py --backup /tmp/head_backup.json --preview /tmp/head_preview.txt
```

Then, only after reading the preview:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/remodel_head.py --backup /tmp/head_backup.json --apply
```

It is idempotent — Telegram answers `MessageNotModified` for a slot that is
already correct — and it handles `FloodWait` by waiting rather than dropping the
edit. The backup file is the only way back: keep it.

## Stage 2 (built, not yet applied)

The superseded uploads are still videos taking up the scroll. A caption cannot
turn a video message into a text message; only deletion can free that space, and
deleting them would renumber nothing but would lose the slots. The owner has
decided to delete them (2026-09-01); `tools/channel/purge_superseded.py` does
it — same `--dup-range` default (`"65-109,126-237"`), same dry-run-by-default
shape as `remodel_head.py`, reusing its `duplicate_title`/`read_manifest` to
identify each candidate's live lesson for the report:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/purge_superseded.py --backup /tmp/purge_backup.json
```

Deletion is irreversible — there is no restore, only the `--backup` JSON
(caption + matched title per id, written before any delete call). `--apply`
is owner-run only, same as `remodel_head.py --apply`.
