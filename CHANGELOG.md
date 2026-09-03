# Changelog

## Unreleased

### Fixed
- `scripts/preview_captions.py` used to `os.chdir()` and `exec_module()`
  `process_and_upload.py` at import time (before `--help` could exit) — this is
  the residual the T-938 entry below recorded as deliberately not fixed. Now
  fixed: the load is lazy, moved into a `_load_uploader()` function called from
  `main()` after `parse_args()`; the `os.chdir()` is kept
  (`process_and_upload.py`'s `STORAGE_DIR = ".storage"` genuinely depends on
  running from the repo root) but scoped with try/finally so the original CWD
  is always restored after the load. Removed `preview_captions.py` from the
  per-file exemption list in `tests/test_entrypoint_cli.py` so the existing
  three static AST tests now cover it unmodified. (T-939)
- T-938: `--help` was not safe to run on 34 of 51 entry points under `scripts/`
  and `tools/` — none of them built an `argparse.ArgumentParser`, so `--help`
  was silently ignored and the script ran for real. A dispatched agent hit
  this spot-checking WO-TVA-0008: `uv run --directory <repo>
  scripts/generate_index.py --help` opened a live Pyrogram connection to
  Telegram and prompted `Enter phone number or bot token:` before crashing on
  EOF, creating `scripts/index_bot.session` (gitignored, since deleted). 10 of
  the 34 had no `if __name__ == "__main__":` guard at all and ran every
  top-level statement on bare import; the other 24 already had a guard but no
  parser. Fixed all 34: every module-level statement that does real work
  (opening a Selenium/Chrome session, a Pyrogram `Client`, `input()`, a file
  write) now runs only inside the guarded entry point, after a
  `parser.parse_args()` that gates it — moved verbatim into `main()` (or the
  `if __name__` block for an `asyncio.run(...)` wrapper) in original order, no
  drops, no reordering; constants still read by other module-level functions
  (e.g. `generate_index.py`'s `STORAGE_DIR`/`MANIFEST_FILE` family) were left
  at module scope untouched. `tools/debug/resolve_channel.py`'s manual
  `sys.argv[1]` positional read became a real
  `argparse` positional (`invite_link`, still falling back to
  `CHANNEL_INVITE_LINK` from `.env`). Left the pre-existing `F821`
  undefined-name bugs in `scripts/retry_failed_uploads.py` untouched (T-934,
  a separate judgment call) and the pre-existing `F811` duplicate-`reconstruct`
  definition in `tools/maintenance/reconstruct_manifest.py` untouched (the
  argparse block was mechanically added to both definitions; only the second,
  live one is ever called). Added `tests/test_entrypoint_cli.py`, three static
  AST tests over every `.py` under `scripts/` and `tools/`: every file builds
  an `ArgumentParser`, every file has a `__main__` guard, and no file makes a
  bare module-level call outside a small allowlist (`load_dotenv`,
  `sys.path.insert`, `logging.basicConfig`, `warnings.filterwarnings`) plus a
  short, named, per-file exemption list for three pre-existing files this WO
  intentionally left untouched (`preview_captions.py`, `process_and_upload.py`,
  `purge_batch.py`) that already gate their own work behind a module-level
  `parser.parse_args()` — a different but equally valid shape. Verified the
  new tests fail on a deliberately reverted file and pass once restored. 77
  passed, 0 failed; `ruff check .` unchanged at 324 findings versus `main`
  (diffed by file+rule, not eyeballed — two mechanical side effects of moving
  code into function scope, an unsorted-import block in 9 files and one
  local variable that was already unused before the move, were fixed/noqa'd
  to keep the count flat). Spot-checked `--help` from outside the repo on the
  three files that used to open live connections
  (`scripts/tg_login.py`, `scripts/generate_index.py`,
  `tools/debug/resolve_channel.py`): usage printed, exit 0, no session file
  created, no prompt. (T-938)

- T-938 residual, deliberately not fixed here: `scripts/preview_captions.py`
  still `os.chdir()`s and dynamically `exec_module()`s
  `scripts/process_and_upload.py` at *import* time, i.e. before its own
  `--help` can exit. It is filesystem-only — the exec'd module has no
  module-level Telegram work (no `Client`, no prompt, no network) — so it
  is not the hazard T-938 was opened for, but it does not satisfy the new
  "`--help` exits before anything happens" contract either. Unwinding it
  means making `_uploader` lazily loaded, a refactor of its own. Recorded
  as a per-file exemption in `tests/test_entrypoint_cli.py` with the
  reasoning inline.
- `build_index()` (`tools/channel/remodel_head.py`) chunked the channel
  index on visible characters only (`LIMIT = 3700`), never on Telegram's
  hard 100-entity-per-message cap. WO-TVA-0006 tripled entities per lesson
  line (number + 📎 resource + subtitle) without updating the chunker, so
  307 of the index's 707 `<a>`/`<b>` entities were silently dropped by
  Telegram past the 100th per post — the links rendered as dead plain text
  with no error. Added an entity counter alongside the char counter and
  close the post when either budget would be exceeded (`ENT_LIMIT = 100`,
  Telegram's hard cap; do not raise it). `INDEX_SLOTS` widened from
  `[4,5,6,7]` to `[4..11]`, absorbing the now-exhausted `HEAD_SPARE`
  (`[]`) — 100 is the only `ENT_LIMIT` value that fits the split into 8
  slots (95 needs 9). Also switched the char budget to UTF-16 code units
  (`len(s.encode("utf-16-le")) // 2`), since Telegram's 4096 cap counts
  those, not Python `len()` — never bit in practice (today's max post is
  under 2100 code units) but the old margin was smaller than it looked.
  Subtitle glyph 📝 -> `CC` in `remodel_head.py` only (`link_captions.py`
  and `attach_resources.py` keep 📝; the 283 live captions aren't being
  re-captioned in this pass, so a temporary mismatch there is expected).
  After the fix the index is 8 posts carrying all 663 links (283 video +
  97 resource + 283 subtitle), entities per post
  `[99, 99, 100, 99, 100, 100, 100, 19]` — three posts sit at exactly the
  cap, so there is no headroom left on either axis. One more lesson needs
  a ninth slot and `build_plan()` will hard-fail by design; see `TODO.md`.
  Because the margin is zero, the pre-split entity prediction also had to
  stop under-counting: a course change emits a section header too, even
  when the section name is unchanged across the boundary, and charging
  only for the course header there put the post at 101 entities — one
  silently dead link. Covered by
  `test_index_entity_cap_holds_across_a_course_boundary`. (T-937)
- `tools/channel/remodel_head.py` could not start at all: `from
  src.env_resolver import env_path` sat *above* the `sys.path.insert(REPO)`
  that makes `src` importable, so the documented invocation
  (`uv run --directory <repo> tools/channel/remodel_head.py ...`) died with
  `ModuleNotFoundError: No module named 'src'` — running a file in a
  subdirectory as a script puts that subdirectory on `sys.path`, never the repo
  root. Introduced by the `.env` vault migration (WO-TVA-0002), which added the
  import at the top of the file; the test suite never caught it because tests
  import the module through `conftest.py`'s path bootstrap. Moved the bootstrap
  above the import. **The same latent break exists in 26 other subdirectory
  entry points** under `scripts/` and `tools/` (`main.py` is fine — it sits at
  the repo root); see T-936. (T-935)
- T-936: the same `sys.path` bootstrap bug fixed in `remodel_head.py` (T-935)
  existed in all 26 other entry points under `scripts/` and `tools/` — either
  the bootstrap was missing entirely, ordered after the first `from src...`
  import, or (in `tools/knowledge/*.py`) present as `sys.path.append(...)`
  instead of `sys.path.insert(0, ...)`, which happened to work but didn't
  match the fix pattern the new regression test enforces. Fixed all 26 to
  `sys.path.insert(0, str(REPO))` before the first `src` import, reusing each
  file's existing repo-root constant where one already existed (e.g.
  `purge_batch.py`'s `ROOT`, also used by `os.chdir(ROOT)`) instead of adding
  a second name for the same path. Added
  `tests/test_entrypoint_bootstrap.py`, a static AST test that walks every
  `.py` under `scripts/` and `tools/` and fails if a module-level `from
  src...`/`import src` line has no `sys.path.insert` strictly before it —
  this is what makes the bug un-reintroducible; verified it fails on a
  deliberately reverted file and passes once restored. 74 passed, 0 failed;
  `ruff check .` unchanged at 325 findings versus `main`. (T-936)
- `pytest` is now a warning gate: `pytest.ini` gets `filterwarnings = error`
  plus a single documented ignore for pyrogram 2.0.106's
  `asyncio.get_event_loop()` DeprecationWarning (raised at import time in
  `pyrogram/sync.py:31`, third-party and unfixable from here — pyrogram is
  unmaintained since 2023). Turning warnings into errors surfaced six real
  unclosed-file leaks (`ResourceWarning`), all now fixed: `open(...)` used as
  an iterator/`.read()` without a context manager in
  `tools/knowledge/check_skill_leak.py` (x2), `tools/knowledge/fetch_resources.py`,
  `tests/test_caption_index.py`, and two bare `open()` calls handed to
  `json.load`/`json.dump` in `tools/channel/remodel_head.py` — the `json.dump`
  one could leave a truncated, unflushed `--apply` backup file behind.
  73 passed, 0 warnings. (T-935)
- Two of T-933's F821 (undefined-name) findings fixed: `scripts/replace_video.py`
  was calling `re.split()` without `import re`. `scripts/process_and_upload.py`
  caught `AuthPasswordInvalid`, a name that doesn't exist anywhere in `pyrogram`
  — the real exception pyrogram raises for a wrong 2FA password is
  `PasswordHashInvalid` (`BadRequest` subclass, matches Telegram's
  `PASSWORD_HASH_INVALID` RPC error), confirmed by inspecting the installed
  `pyrogram.errors` module. The other 16 F821 findings (`scripts/scraper.py`,
  `scripts/retry_failed_uploads.py`) need a human read of intended behavior
  first — see `WO-TVA-0005`. (T-934)
- `tests/test_preview_gen.py` was a module-level script with no `def test_...()`
  function, so it ran at pytest **collection** time on every test run, wrote a
  tracked binary (`title_preview.png`) into the repo root as a side effect, and
  asserted nothing. Rewrote it as a real test (`test_preview_generation`) that
  renders into pytest's `tmp_path` fixture and asserts image size/mode and
  output-file presence. Untracked `title_preview.png` from git and added it to
  `.gitignore`. (T-932)

### Added
- The channel index (`build_index` in `tools/channel/remodel_head.py`) now also links each lesson's resources (📎) and subtitles (📝) next to the lesson number. It reuses the same `pack_parts` → `duplicate_note` → `subtitle` precedence that `tools/knowledge/link_captions.py` already uses for the caption link. The links are sourced from `data/attachments_state.json`.
- New tool `tools/channel/purge_superseded.py` — Stage 2 of the channel remodel
  (`docs/CHANNEL-LAYOUT.md`): deletes the superseded-upload videos in id ranges
  `65-109` and `126-237` that Stage 1 (`remodel_head.py`) only re-captions.
  Reuses `remodel_head.py`'s `duplicate_title`/`read_manifest` for candidate
  identification, follows `scripts/purge_batch.py`'s dry-run/`--apply`/FloodWait
  shape. Dry-run by default; writes a `--backup` JSON (caption + matched title
  per id) before any delete call, and aborts before deleting if the backup
  write fails. Dry run against the live channel confirms 71 candidate messages
  under the current default ranges; `--apply` has not been run — that's an
  owner-run step, same as `remodel_head.py --apply`. (WO-TVA-0007)
- `ruff` added as a dev dependency (`[dependency-groups] dev`) with a minimal
  `[tool.ruff]` section (no custom rule overrides — plain ruff defaults) to
  give this repo its first lint gate. Ran `ruff check --fix .` and committed
  the resulting mechanical fixes (import sorting/formatting, `str(e)` ->
  `e!s`, redundant f-string prefixes removed, `str.removeprefix()` in place
  of manual slicing, unreachable `pass` after a comment-only block). No
  runtime behavior changed — full test suite still passes (63 passed).
  333 residual findings remain (mostly exception-handling style: blind/bare
  `except`, `try/except/pass`) that need a human judgment call rather than an
  automated fix; see T-933 handoff report for the full breakdown by rule
  code. (T-933)
