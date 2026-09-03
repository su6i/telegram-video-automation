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
| `4`–`11` | The index. 283 lessons in 34 sections currently fill **8** posts |
| `65`–`109`, `126`–`237` | Superseded uploads from earlier runs. Stage 1 does **not** delete them; each caption is rewritten to say so and, where the title still matches the manifest, to link the live lesson |
| `111`–`125` | A divider: block art, then further spare slots |
| `291`–`305` | Tail spare, immediately above the library. The last one is the "library starts here" signpost |
| `306`+ | The library: 283 lessons, then their resources and subtitles |

## Sizing the index

Do not guess. Two independent budgets apply, and a post closes when either
would be exceeded:

- **Characters.** One index line is a lesson number plus a title (~40
  visible characters, counted in UTF-16 code units — Telegram's 4096 cap
  counts those, not Python `len()`); a section header adds ~30. The tool
  packs to `LIMIT = 3700`, splitting a long section across posts and
  repeating its header with `(continued)`.
- **Entities.** Telegram allows at most **100 message entities** (`<a>`,
  `<b>`, ...) per message and silently drops the rest — no error, no
  truncation marker, the text renders with dead plain-text where the links
  should be. Every lesson line costs 1 entity for the number link, +1 if it
  has a resource link, +1 if it has a subtitle link; every course/section
  header costs 1. `ENT_LIMIT = 100` is Telegram's hard cap and is not
  adjustable — in practice this drives most splits today, well before the
  character budget is ever reached.

At 283 lessons across 34 sections that is 8 posts, against 8 reserved index
slots (`INDEX_SLOTS`, which absorbed the former `HEAD_SPARE`). **When the
index needs a ninth post the tool refuses to run** and says so — the head
spare is exhausted, so growing further means reclaiming ids `12`–`64`,
which no state file references and which sit below the first real lesson
video (id `306`). That is an owner decision and needs a live read of what
those messages currently hold before any of them is reused. Note also that
`purge_superseded.py` permanently removes ids in `65`–`109` / `126`–`237`,
and a deleted message can never be edited again — purging shrinks the pool
of future index slots. The tool will never silently overwrite a video.

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
