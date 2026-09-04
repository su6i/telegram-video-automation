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
| `12`–`64` | **Deleted. Not slots.** Nothing can ever live here again |
| `70`, `84`, `90`, `93`, `99`, `101`, `103`, `107` | Index spare — the 8 reclaimed orphans (T-940). Because `12`–`64` are deleted and leave no visual trace, these render directly under slot `11`, so the index can grow into them and still read as one block |
| `111`–`125` | A divider: block art, then further spare slots |
| `133`, `186`, `211`, `216`, `224`, `226`, `230`, `232`, `235`, `237` | Mid spare — the other 10 reclaimed orphans (T-940). Below the divider, so they are *not* index capacity |
| `238`–`290` | **Deleted. Not slots.** |
| `291`–`305` | Tail spare, immediately above the library. The last one is the "library starts here" signpost |
| `306`+ | The library: 283 lessons, then their resources and subtitles |

## The bottom index — republished, not reserved (T-943)

There used to be a second index fixed to ids `685`-`691` — 7 slots, a hard
700-entity ceiling, which is why it could carry the title link + CC subtitle
link but not the 📎 resource link (see the superseded arithmetic below). The
owner's call (2026-09-04): stop treating the bottom index as fixed real
estate. `tools/channel/publish_bottom_index.py` now **republishes it after
every upload batch** — it posts a fresh copy at the very end of the channel,
deletes the previous copy, and moves the pin — so it is always the channel's
last messages, can never be buried, and carries the same full-parity line as
the head index (title link + 📎 resource + CC subtitle) with **no slot
ceiling** (`src/index_builder.UNBOUNDED`).

The ordering is the safety property: new posts are sent, silently
(`disable_notification=True`), **before** the old ones are deleted, and the
pin only moves after the delete succeeds. A crash between "post" and "delete"
leaves the channel with two indexes — redundant, never absent. The tool's own
state file (`data/bottom_index_state.json` in the vault) tracks which ids are
currently the live bottom index; on its very first run it is seeded with the
legacy `685`-`691`, which are deliberately **never passed to delete** (see
below) — every later cycle deletes the previous cycle's own posts instead.

Ids `685`-`691` themselves are not deleted, ever: `remodel_head.py` now
repurposes them as `POST_LIBRARY_SLOTS` — a "📎 Resources start here"
signpost plus 6 spare editable slots, immediately above the resource-document
block (`692+`, which can never become editable text again). Deleting one of
the seven instead would have made that id permanently un-editable, for no
benefit.

**Run order on the first cycle, and only the first.** Because `685`-`691` are
never deleted, the very first `publish_bottom_index.py --apply` leaves their
old "📚 Video List" text sitting in the channel while the new index is live at
the end — two visible indexes, one of them stale. `remodel_head.py --apply` is
what clears that: it overwrites the seven with the signpost and spare slots.
So on the first cycle run `publish_bottom_index.py --apply` **then**
`remodel_head.py --apply`, and do not stop in between. Every later cycle is
self-contained — it deletes its own previous posts — and needs no companion
run.

Dry run (no network at all — the tool only reads the local manifest and the
vault's state files):

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/publish_bottom_index.py
```

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/publish_bottom_index.py --backup /tmp/bottom_index_backup.json --apply
```

*Superseded arithmetic, kept for the record:* under the old fixed-7-slot
design the index carried 342 entities → 625/700 after adding CC subtitle
links; adding 📎 resource links too would have needed 722, over budget, and
stripping bold headers to make room was rejected. None of this applies once
the slot ceiling is gone.

## Sizing the index

Do not guess. Two independent budgets apply, and a post closes when either
would be exceeded (the chunker is now shared between both indexes via `src/index_builder.py`, so they can no longer drift silently):

- **Characters.** One index line is a lesson number plus a title (~40
  visible characters, counted in UTF-16 code units — Telegram's 4096 cap
  counts those, not Python `len()`); a section header adds ~30. The tool
  packs to `LIMIT = 3700`, splitting a long section across posts and
  repeating its header with `(continued)`.
- **Entities.** Telegram allows at most **100 message entities** (`<a>`,
  `<b>`, ...) per message and silently drops the rest — no error, no
  truncation marker, the text renders with dead plain-text where the links
  should be. Every lesson line costs 1 entity for the lesson-title link, +1 if it
  has a resource link, +1 if it has a subtitle link; every course/section
  header costs 1. `ENT_LIMIT = 100` is Telegram's hard cap and is not
  adjustable — in practice this drives most splits today, well before the
  character budget is ever reached.

At 283 lessons across 34 sections that is 8 posts, against **16** index slots
(`INDEX_SLOTS`: the original `4`–`11`, which had already absorbed the former
`HEAD_SPARE`, plus the 8 orphans reclaimed in T-940). **When the index needs a
seventeenth post the tool refuses to run** and says so. There is no further
reserve behind that: ids `12`–`64` and `238`–`290` are deleted end to end
(verified live 2026-09-03), and *a deleted message can never be edited again*,
so the "reclaim `12`–`64`" growth path earlier versions of this document
promised does not exist. Past 16 posts the only options are `MID_SPARE` — 10
slots, but they sit below the divider, so the index would stop reading as one
block — or appending new messages below the library. The tool will never
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

## Stage 2 (applied 2026-09-03)

The superseded uploads were videos taking up the scroll. A caption cannot turn a
video message into a text message; only deletion frees that space. The owner
decided to delete them (2026-09-01) and ran
`tools/channel/purge_superseded.py --apply` on 2026-09-03 — 71 video messages in
`65`–`109` / `126`–`237` are gone. Deletion is irreversible; the only record is
the `--backup` JSON (caption + matched title per id, written before any delete
call). `--apply` is owner-run only, same as `remodel_head.py --apply`.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/purge_superseded.py --backup /tmp/purge_backup.json
```

## Stage 3 — the reclaimed orphans (T-940)

`purge_superseded.py` only deletes messages that carry a video
(`filter_video_candidates`). Back when captions overflowed Telegram's 1024-char
limit, the remainder was posted as a **separate text message** right after the
video. Those continuation messages have no video, so the purge correctly left
them alone — and their parent videos are now gone, leaving 18 orphans reading
`📄 Continued: …` with nothing above them.

A live census of ids `1`–`305` on 2026-09-03 found exactly what survives:

| Band | Live | Deleted |
|---|---|---|
| `2`–`3` banner/about | 2 | 0 |
| `4`–`11` index | 8 | 0 |
| `12`–`64` | 0 | 53 |
| `65`–`109` | **8 orphans** | 37 |
| `110`–`125` divider | 15 (+1 service) | 0 |
| `126`–`237` | **10 orphans** | 102 |
| `238`–`290` | 0 | 53 |
| `291`–`305` tail | 15 | 0 |

An orphan is an ordinary editable text message, so all 18 became reserve slots:
the 8 in `65`–`109` extend `INDEX_SLOTS` (8 → 16 posts of index capacity), the
10 in `126`–`237` become `MID_SPARE`. This is the whole reserve — the two dead
bands above are dead for good.

Re-running `remodel_head.py` is what converts them; the run is 58 text edits and
0 caption edits (there are no superseded videos left to re-caption).
