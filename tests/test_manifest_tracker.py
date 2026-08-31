"""The manifest carries two line formats; every reader must handle both."""
import pytest

from src import manifest_tracker as mt

MANIFEST = """# Index | Title | URL
# === Course A ===

## --- Section One ---
001_Compact Pending | https://a
002 | Expanded Pending | https://b
003 | Expanded Done | https://c | ✅ UPLOADED (msg_id: 42)
004_Compact Failed | https://d | ❌ FAILED
# [DONE] 005_Legacy Done | https://e
# 006_Skipped | https://f
"""


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    path = tmp_path / "downloaded_video.txt"
    path.write_text(MANIFEST, encoding="utf-8")
    monkeypatch.setattr(mt, "MANIFEST_FILE", str(path))
    return path


def test_pending_covers_both_line_formats(manifest):
    assert [v["index"] for v in mt.get_pending_videos()] == ["001", "002"]
    assert mt.get_pending_videos()[0]["title"] == "Compact Pending"
    assert mt.get_pending_videos()[0]["url"] == "https://a"


def test_uploaded_includes_the_legacy_done_prefix(manifest):
    assert [v["index"] for v in mt.get_uploaded_videos()] == ["003", "005"]


def test_failed_reads_a_compact_line(manifest):
    assert [v["index"] for v in mt.get_failed_videos()] == ["004"]


def test_status_is_none_while_pending(manifest):
    assert mt.get_video_status("001") is None
    assert "UPLOADED" in mt.get_video_status("003")


def test_headers_and_comments_are_not_videos(manifest):
    videos = mt.get_all_manifest_videos()
    assert [v["index"] for v in videos] == ["001", "002", "003", "004", "005"]
    assert videos[0]["course"] == "Course A"
    assert videos[0]["section"] == "Section One"
    assert videos[0]["url"] == "https://a"
    assert [v["is_done"] for v in videos] == [False, False, True, False, True]


def test_a_compact_line_becomes_uploaded_after_recording(manifest):
    assert mt.update_manifest_status("001", "UPLOADED", msg_id=7) is True
    assert [v["index"] for v in mt.get_pending_videos()] == ["002"]
    assert mt.get_video_status("001") == "✅ UPLOADED (msg_id: 7)"
