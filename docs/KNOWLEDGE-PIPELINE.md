# Knowledge pipeline

Turns a video library into reusable material: transcripts, subtitles, the
resources the lessons link to, and — after distillation — agent skills.

Everything it produces is personal data and lands in the **vault**, never in
this repository (rule 035):

```
<vault>/telegram-video-automation/data/
├── transcripts/   NNN_title.json   full text + timed segments
├── subtitles/     NNN_title.srt    generated from the transcripts
├── resources/NNN/                  worksheets/templates the lesson links to
├── audio/                          scratch only; not kept
├── message_ids.json                 {lesson index: Telegram message id}
└── attachments_state.json           what's been sent per lesson, for resuming
```

## 1. Transcribe

Local, on Apple Silicon, no API cost. Measured **15x realtime** with
`whisper-large-v3-turbo` on an M4, i.e. ~4.5 h for a 67 h library.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation --with mlx-whisper tools/knowledge/transcribe_library.py --videos /Volumes/Archive/_release_2026-08 --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/transcripts --mem-limit-gb 6 --cache-limit-gb 1
```

Resumable — an existing transcript is skipped, so the run survives an
interruption. The model is loaded once for the whole run.

**Always pass the memory caps.** MLX keeps freed buffers in a reuse cache that
is unbounded by default: an uncapped run climbed to a 12 GB footprint and put
the machine into swap. With `--mem-limit-gb 6 --cache-limit-gb 1` the same run
peaks at ~2 GB, which the per-lesson log line reports. The defaults are those
values; `--mem-limit-gb 0` removes the cap.

## 2. Subtitles

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/make_subtitles.py --transcripts /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/transcripts --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/subtitles --zip
```

## 3. Linked resources

Downloads the shared-drive files a lesson links to, one directory per lesson
index. Permission-restricted links are recorded in `failures.json` rather than
stopping the run.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/fetch_resources.py --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/resources
```

`--retry-failed` re-runs only the links in `failures.json`. A lesson that failed
part-way already has files on disk, so the normal run skips it; the retry forces
those lessons and `gdown --continue` resumes the partial download. When every
retried link succeeds the file is removed, so a fixed lesson does not stay listed
as failed forever.

A drive folder can be several GB, and gdown's progress bar goes to a pipe that
is only read at the end — so a healthy download looks frozen. The log line per
link reports the bytes and minutes it took, which is what distinguishes a slow
download from a stuck one. `--timeout` (default 7200 s) bounds one link; a
timeout is now recorded as a failure and the partial files are resumed on the
next pass instead of killing the run.

## 4. Attach resources & subtitles under each video message

Replies the deduped resource packs and the subtitle file onto the video
message the lesson was originally uploaded as, so everything for a lesson
lives in one Telegram thread.

**a. Map lesson index -> Telegram message id.** Combines the backup caption
export with a live channel scan, and prints how many lessons are mapped vs.
still missing. Both halves read the index through `src/caption_index.py`, so
the export alone now maps every lesson it contains; the scan still matters,
because a lesson re-uploaded after the export was taken has a newer message id
and the scan is applied last so it wins.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/message_map.py --source both --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/message_ids.json
```

Only video messages are mapped. The index posts open with their own first entry
(`001 - Welcome!`), so a scan that read text messages too mapped lesson 001 to
the table of contents and replied that lesson's attachments onto the wrong
message.

`--backup` defaults to `backup_captions.json` next to `--out`; pass it only when
the file lives elsewhere. The index is taken from whichever header line carries
it, because the early uploads open with `NNN - Title` while the later ones carry
it on the third header line — matching only the first line mapped 36 of 283
lessons. The run prints how many messages it saw, how many carried an index and
how many distinct lessons came out of it.

`attach_resources.py --only NNN` (repeatable) restricts a run to single lessons.
Send one small lesson with `--only` before the full run: `--go` is owner-only and
every message it sends is a real message in the channel. Naming a duplicate
lesson keeps its canonical in the run, otherwise its pointer message would have
nothing to point at. The scan half needs the pyrogram session, so it fails
with `database is locked` while an upload run holds it — stop that run first.

**b. Review the plan.** Dedupes identical resource-pack directories (several
lesson folders can be byte-identical copies of the same asset pack), plans
the zip parts (capped at `--max-part-gb`, default 1.8 — the 2 GB Telegram
user-account file limit minus headroom), and prints what it would send,
without writing a zip, touching the state file, or opening a Telegram
connection. `--dry-run` is the default — always run it first:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/attach_resources.py --resources /Volumes/Archive/_release_2026-08/_resources --subtitles /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/subtitles --map /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/message_ids.json --state /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/attachments_state.json --dry-run
```

**c. Send — owner-only.** Same command with `--go` in place of `--dry-run`:
zips each canonical pack (skipping a part that already exists), replies it
under the lesson's video message, replies a link to the canonical message
for every duplicate lesson, and attaches the subtitle. Resumable and fault
tolerant — `attachments_state.json` (in the vault) records what has been
sent per lesson, so a second run only retries what's missing or failed; one
failed send is logged and does not stop the run. **Nobody but the owner runs
`--go`** — an agent must never pass it, since it sends to the real channel.

Each zip is written under a `.part` name and renamed only when it is complete,
and an existing zip is trusted only if its central directory is readable — a run
killed mid-zip used to leave a truncated file that the next run skipped as
"already built" and uploaded corrupt. Already-compressed members (video, audio,
images, archives) are stored rather than deflated; deflating them again cost
minutes of CPU per gigabyte and saved nothing.

A run of a few hundred messages trips Telegram's rate limit; the sender waits
out each `FloodWait` and retries rather than recording it as a failure, and
`--delay` (2 s by default) paces the run between sends.

The run has three passes: **A** sends each canonical lesson's pack parts and
subtitle, **B** sends a pointer to the canonical pack for every duplicate
lesson, and **C** sends the subtitle of every lesson that has one but no
resources at all — which is most of them (99 lessons have resources, 285 have
a subtitle), and which A and B never visit.

Lesson indexes that have resources or a subtitle but no entry in
`message_ids.json` are printed at the end of every run — that list is the
input for the pinned index message that covers what couldn't be
auto-attached.

## 5. Point each video's caption at its attachments

A Telegram channel only ever appends. A reply posted after the channel was
filled lands at the end of the history no matter which message it quotes, so
step 4's attachments sit hundreds of messages below the lesson they belong to.
Editing the video's own caption is the one way to put the pointer where the
reader already is; the alternative is reposting the whole channel in order,
which breaks every link that has been shared.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/link_captions.py --map /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/message_ids.json --state /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/attachments_state.json --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/caption_links_state.json --dry-run
```

Each caption gains one line — `📎 Resources & subtitles`, or `📝 Subtitles` for
a lesson that only has one — linking to the lesson's first attachment message.
`--dry-run` is the default and opens no Telegram connection; `--go` edits real
messages. It is idempotent from two directions: the local state file, and the
live caption itself, so a lost state file cannot double-append. A caption too
close to Telegram's 1024-character limit falls back to a shorter label and, if
even that does not fit, is reported and left alone.

## 6. Distillation into skills — rules

The transcripts are someone else's teaching. What may leave the vault is
**procedural knowledge in our own words**: the method, the decision rules, the
checklist. What may never leave it is the expression — no transcript text, no
lesson titles, no course, site or instructor names, no quoted passages.

### Batching

Distillation is an LLM job over ~4.1M characters (~1.0M tokens), so it belongs
on a $0 worker, not in an architect session. `distill_batches.py` does the
deterministic half: it groups the transcripts the way the course already groups
them — one batch per section, which is the shape a skill takes — and writes a
self-contained prompt per batch.

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/distill_batches.py --out /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/distill
```

34 sections become 49 batches (a section over `--max-chars`, 120k by default,
splits into parts). Housekeeping sections — course intros, discount codes,
community links — teach nothing transferable and are dropped. Each batch is one
worker call; the batches carry transcript text, so they live in the vault.

### The gate

`agent-constitution` is a public repository, so a generated skill is checked
before it is committed there. `check_skill_leak.py` is that gate and exits
non-zero on any hit:

```bash
uv run --directory /Users/su6i/@-github/telegram-video-automation tools/knowledge/check_skill_leak.py --skill /Users/su6i/@-github/agent-constitution/skills/<name>.md --transcripts /Users/su6i/.local/share/agent-projects/telegram-video-automation/data/transcripts
```

Two checks, because they fail differently. The **banned-term scan** catches the
names, and derives them from the manifest (course, section and lesson titles)
and the transcript metadata rather than a hand-kept list, so it cannot drift out
of date; `--extra-terms` points at a vault file for instructor and site names,
which must never be committed here. The **n-gram overlap test** catches copied
phrasing no name list would contain — any run of `--n` words (8 by default)
shared with the corpus is a hit. Fenced and inline code is excluded from both,
since a command carries no source expression.

The corpus is ~780,000 8-grams over 285 transcripts and builds in a few seconds,
so the gate is cheap enough to run on every skill, every time.
