# Changelog

## Unreleased

### Fixed
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
