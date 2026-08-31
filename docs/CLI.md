# Telegram Video Automation CLI

The `main.py` entry point acts as the unified CLI for all operations.

## Setup
```bash
uv sync
```

## Usage
Run the CLI using `uv run main.py`:

```bash
uv run main.py [input_url] [options]
```

### Options
- `--url`: Download a single lesson.
- `--scan`: Scan the target site and update the video manifest.
- `--download`: Batch download videos from the manifest.
- `--archive`: Archive HTML pages listed in the manifest.
- `--force`: Force overwrite existing files.
- `--limit`: Limit operations to N items.
- `--visible`: Run Chrome in visible mode.
- `--verbose`: Enable debug logging.

## Examples
### Download a Single Lesson
```bash
uv run main.py "https://example.com/lesson" --visible
```

### Batch Processing
```bash
uv run main.py --scan
uv run main.py --download
uv run main.py --archive
```

## Uploading to Telegram

`scripts/process_and_upload.py` walks the manifest in order and uploads each
lesson to the configured channel.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/process_and_upload.py --res 1080
```

### Options
- `--res {720,1080}`: target resolution. **Defaults to `720`.** Files already
  staged in `processed/` at a higher resolution are discarded and re-encoded
  when this does not match, so pass `--res 1080` for a 1080p library.
- `--dry-run`: list what would be uploaded, touch nothing.
- `--intro`: prepend the intro clip (forces a re-encode).
- `--cleanup`: remove staged files from `processed/` after a successful upload.
- `--log FILE`: mirror output to `.storage/FILE`.

### Caption behaviour
Each video is sent with a caption built from the manifest and from the lesson
page text stored in `.storage/scraped_content.json`:

```
**Course**
**Section**
**NNN - Lesson title**

🔗 Links:
• [anchor](url)

📝 Info:
<lesson page text>
```

Telegram caps a media caption at 1024 characters. When the page text does not
fit, the caption is cut on a paragraph/sentence boundary and the remainder is
sent **immediately after the video**, as replies to it, split into
`Continued (n/m)` messages of at most 3800 characters each. Nothing is
truncated — every chunk after the first replies to the previous one so the
whole description stays contiguous under the video.

A lesson with no entry in `scraped_content.json` uploads with a title-only
caption, so re-scan the site before an upload run if lessons were added.

The caption is cut only on a boundary that leaves the Markdown intact: a cut
inside `**a header**` or `[a link](url)` would publish a stray `**` or a raw
URL, so such a boundary is rejected and an earlier one is used.

### Preview the captions before uploading — do this every run
`scripts/preview_captions.py` renders every caption through the same
`src/caption_builder.build_caption()` the uploader calls, without touching
Telegram. Anything it prints is exactly what the channel would receive.

```bash
# full report to a file
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/preview_captions.py --out /tmp/captions.txt

# a single lesson
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/preview_captions.py --index 013

# machine check only: exits 1 if any caption leaks a sentinel or breaks the limit
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/preview_captions.py --check
```

`--check` catches unrestored link placeholders, leftover `CLICK HERE` labels,
bullets with no text, orphaned punctuation lines and over-length captions. It
is a floor, not a substitute for reading a sample of the report.

### Undoing an upload run
`scripts/purge_batch.py` removes what one run put into the channel: the videos
listed in `.storage/upload_history.json`, the reserved index placeholders, and
the `Continued` overflow replies (following the reply chain, so no orphan part
2/2 is left). Everything else in the channel is listed as KEEP and never
touched. It prints the plan and deletes nothing without `--apply`; on `--apply`
it also resets `upload_history.json` so the next run starts at 001.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/purge_batch.py
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/purge_batch.py --apply
```

### One-time Telegram login
Uploads over 45 MB go through a real user account, which needs a Pyrogram
session file. Create it once, interactively:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation scripts/tg_login.py
```

Answer with your **phone number** (not a bot token) and the login code Telegram
sends you. The session is written to `hybrid_account.session` in the repo root
and reused by every later upload run.

### Channel targeting
`CHANNEL_ID` in `.env` is authoritative. A freshly created Pyrogram session has
an empty peer cache, so the first `get_chat(<raw id>)` fails with
`Peer id invalid`; the resolver now walks the dialog list once to prime the
cache and retries **the same id**. If that id is still unreachable the run
aborts — it never falls back to another channel from the account. The
dialog-scan heuristic runs only when no `CHANNEL_ID`, `INVITE_LINK` and
`CHANNEL_USERNAME` are configured at all.

`--dry-run` never writes to Telegram: it skips both the reserved index
placeholders and the follow-up index update.

### Channel head

Rewrite the banner, the about post, the full index and the reserved slots above
the library. Dry run by default; see `docs/CHANNEL-LAYOUT.md` for the slot map.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/remodel_head.py --backup /tmp/head_backup.json --preview /tmp/head_preview.txt
```

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/channel/remodel_head.py --backup /tmp/head_backup.json --apply
```
