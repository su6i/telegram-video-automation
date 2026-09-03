import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "channel"))

from remodel_head import build_index, resource_and_subtitle_ids, visible


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

    assert '<a href="https://t.me/c/1/100">001</a> <a href="https://t.me/c/1/200">📎</a> <a href="https://t.me/c/1/201">CC</a> · Intro' in post
    assert '<a href="https://t.me/c/1/101">002</a> · Next' in post


def _entity_count(post):
    return len(re.findall(r"<a ", post)) + len(re.findall(r"<b>", post))


def _utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def test_index_splits_on_entities_not_only_chars():
    # 110 short lines, one course/section: visible chars stay tiny (never
    # near LIMIT) but entities (110 lesson links + 2 headers = 112) blow
    # past ENT_LIMIT=100. A char-only chunker fails this: it never splits,
    # producing one post with well over 100 entities. This is the
    # regression that actually pins T-937.
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 111)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 111)}
    attach_state = {}
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state)
    assert len(posts) > 1
    for post in posts:
        assert _entity_count(post) <= 100


def test_index_respects_entity_cap():
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 111)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 111)}
    attach_state = {}
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state)
    for post in posts:
        assert _entity_count(post) <= 100
        assert _utf16_len(visible(post)) <= 4096


def test_index_emits_every_link():
    entries = [
        ("Course A", "Section 1", "001", "Intro"),
        ("Course A", "Section 1", "002", "Next"),
        ("Course A", "Section 1", "003", "No video"),
    ]
    msg_of = {"001": 100, "002": 101}  # "003" has no mid -> plain text, 0 links
    attach_state = {
        "001": {"pack_parts": {"1": 200}, "duplicate_note": None, "subtitle": 201},
        "002": {"pack_parts": {}, "duplicate_note": None, "subtitle": None},
        "003": {"pack_parts": {}, "duplicate_note": None, "subtitle": None},
    }
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state)
    total_links = sum(post.count("<a href") for post in posts)
    # 001: mid + resource + subtitle = 3 links. 002: mid only = 1 link.
    # 003: no mid = 0 links. Total = 4, none silently dropped.
    assert total_links == 4


def test_index_entity_cap_holds_across_a_course_boundary():
    # A course change always emits a section header too, even when the
    # section name is unchanged across the boundary. If the pre-split
    # entity prediction charges only for the course header, the post
    # lands at 101 entities and Telegram drops the 101st link in silence.
    #
    # The fixture is tuned to sit exactly on that edge: course 0 leaves the
    # post at 98 entities (1 course header + 1 section header + 96 lesson
    # links), so the first lesson of course 1 is predicted to cost 2
    # (course header + link) and fit at 100 — while it actually costs 3,
    # because the course header forces a section header even though the
    # section name did not change.
    entries = [("Course 0", "Shared Section Name", f"{i:03d}", "X")
               for i in range(1, 97)]
    entries += [("Course 1", "Shared Section Name", f"{i:03d}", "X")
                for i in range(97, 103)]
    msg_of = {num: 1000 + n for n, (_, _, num, _) in enumerate(entries)}
    posts = build_index(entries, msg_of, internal=1, attach_state={})
    for post in posts:
        assert _entity_count(post) <= 100
