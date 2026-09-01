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
