import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "channel"))

from remodel_head import build_index, resource_and_subtitle_ids


def test_resource_and_subtitle_ids_with_pack_parts():
    entry = {"pack_parts": {"2": 702, "1": 701}, "subtitle": 703}
    assert resource_and_subtitle_ids(entry) == (701, 703)


def test_resource_and_subtitle_ids_with_duplicate_note():
    entry = {"pack_parts": {}, "duplicate_note": 710, "subtitle": 711}
    assert resource_and_subtitle_ids(entry) == (710, 711)


def test_resource_and_subtitle_ids_with_no_parts_or_note():
    entry = {"pack_parts": {}, "duplicate_note": None, "subtitle": 720}
    assert resource_and_subtitle_ids(entry) == (None, 720)


def test_resource_and_subtitle_ids_with_none():
    assert resource_and_subtitle_ids(None) == (None, None)
    assert resource_and_subtitle_ids({}) == (None, None)


def test_build_index_glyph_output():
    entries = [
        ("Course A", "Section 1", "001", "Intro"),
        ("Course A", "Section 1", "002", "Next"),
    ]
    msg_of = {"001": 100, "002": 101}
    attach_state = {
        "001": {"pack_parts": {"1": 200}, "duplicate_note": None, "subtitle": 201},
        "002": {"pack_parts": {}, "duplicate_note": None, "subtitle": None},
    }
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state)

    assert len(posts) == 1
    post = posts[0]

    assert '<a href="https://t.me/c/1/100">001</a> <a href="https://t.me/c/1/200">📎</a> <a href="https://t.me/c/1/201">📝</a> · Intro' in post
    assert '<a href="https://t.me/c/1/101">002</a> · Next' in post
