# Changelog

## Unreleased

### Fixed
- `tests/test_preview_gen.py` was a module-level script with no `def test_...()`
  function, so it ran at pytest **collection** time on every test run, wrote a
  tracked binary (`title_preview.png`) into the repo root as a side effect, and
  asserted nothing. Rewrote it as a real test (`test_preview_generation`) that
  renders into pytest's `tmp_path` fixture and asserts image size/mode and
  output-file presence. Untracked `title_preview.png` from git and added it to
  `.gitignore`. (T-932)

### Added
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
