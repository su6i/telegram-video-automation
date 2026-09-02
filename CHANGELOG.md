# Changelog

## Unreleased

### Fixed
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
