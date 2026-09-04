import re
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "channel"))

from remodel_head import (
    ABOUT_SLOT,
    BANNER_SLOT,
    DIVIDER_SLOTS,
    HEAD_SPARE,
    INDEX_SLOTS,
    MID_SPARE,
    POST_LIBRARY_SIGNPOST,
    POST_LIBRARY_SLOTS,
    TAIL_SPARE,
    build_plan,
)

from src.index_builder import (
    build_index,
    resource_and_subtitle_ids,
    visible,
)


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

    assert '001 <a href="https://t.me/c/1/200">📎</a> <a href="https://t.me/c/1/201">CC</a> · <a href="https://t.me/c/1/100">Intro</a>' in post
    assert '002 · <a href="https://t.me/c/1/101">Next</a>' in post


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


def test_slot_map_has_no_deleted_ids_and_no_overlap():
    """T-940: the reclaimed orphans are real, editable ids — 12-64 and 238-290
    are deleted end to end (verified live 2026-09-03) and must never appear in
    any slot list, because a deleted message can never be edited back."""
    dead = set(range(12, 65)) | set(range(238, 291))
    pools = {"INDEX_SLOTS": INDEX_SLOTS, "HEAD_SPARE": HEAD_SPARE,
             "DIVIDER_SLOTS": DIVIDER_SLOTS, "MID_SPARE": MID_SPARE,
             "TAIL_SPARE": TAIL_SPARE}
    for name, pool in pools.items():
        assert not dead.intersection(pool), f"{name} claims a deleted id"

    all_slots = [BANNER_SLOT, ABOUT_SLOT] + [s for p in pools.values() for s in p]
    assert len(all_slots) == len(set(all_slots)), "a slot id is claimed twice"
    assert max(all_slots) < 306, "a slot reaches into the library"
    assert INDEX_SLOTS == sorted(INDEX_SLOTS), "index posts must read in id order"


def test_reclaimed_index_slots_are_used_before_mid_spare():
    """The 8 orphans in 65-109 extend the index because 12-64 is deleted, so
    they render directly under slot 11. MID_SPARE sits below the divider and is
    deliberately not index capacity."""
    assert len(INDEX_SLOTS) == 16
    assert INDEX_SLOTS[8:] == [70, 84, 90, 93, 99, 101, 103, 107]
    assert max(INDEX_SLOTS) < min(DIVIDER_SLOTS)
    assert min(MID_SPARE) > max(DIVIDER_SLOTS)


def test_remodel_head_includes_post_library_slots():
    entries = [("Course A", "Section 1", "001", "Intro")]
    msg_of = {"001": 100}
    dup_ids = {}
    live_by_title = {}
    attach_state = {}
    plan, _ = build_plan(entries, msg_of, 1, dup_ids, live_by_title, attach_state)
    
    post_lib_entries = [p for p in plan if p[0] in POST_LIBRARY_SLOTS]
    assert len(post_lib_entries) == len(POST_LIBRARY_SLOTS)
    
    assert post_lib_entries[0][0] == POST_LIBRARY_SLOTS[0]
    assert post_lib_entries[0][2] == POST_LIBRARY_SIGNPOST
    
    for i in range(1, len(POST_LIBRARY_SLOTS)):
        assert post_lib_entries[i][0] == POST_LIBRARY_SLOTS[i]
        assert "POST-LIBRARY SPARE" in post_lib_entries[i][2]


def test_spare_content_queue_shifts_by_one_slot_when_index_grows(monkeypatch):
    import remodel_head
    content_items = [{"key": "x", "title": "T", "body_html": "hello", "links": []}]
    
    monkeypatch.setattr(remodel_head, "build_index_or_fail", lambda *a, **kw: ["p0"])
    plan_a, _ = build_plan([], {}, 1, {}, {}, {}, content_items=content_items)
    
    monkeypatch.setattr(remodel_head, "build_index_or_fail", lambda *a, **kw: ["p0", "p1"])
    plan_b, _ = build_plan([], {}, 1, {}, {}, {}, content_items=content_items)
    
    slot_a = next(slot for slot, _, body in plan_a if "hello" in body)
    slot_b = next(slot for slot, _, body in plan_b if "hello" in body)
    assert slot_a == INDEX_SLOTS[1]
    assert slot_b == INDEX_SLOTS[2]


def test_content_over_entity_budget_hard_fails():
    item = {
        "key": "x", "title": "T",
        "body_html": " ".join(f"link{i}" for i in range(105)),
        "links": [{"text": f"link{i}", "lesson": f"{i:03d}"} for i in range(105)]
    }
    msg_of = {f"{i:03d}": 1000 + i for i in range(105)}
    from remodel_head import render_content_post
    with pytest.raises(SystemExit):
        render_content_post(item, msg_of, 1)


def test_content_over_char_budget_hard_fails():
    item = {
        "key": "x", "title": "T",
        "body_html": "X" * 5000,
        "links": []
    }
    from remodel_head import render_content_post
    with pytest.raises(SystemExit):
        render_content_post(item, {}, 1)


def test_slot_past_queue_end_renders_plain_spare():
    plan, _ = build_plan([], {}, 1, {}, {}, {}, content_items=[])
    assert any("Reserved slot" in body for _, _, body in plan)


def test_content_item_never_lands_outside_the_four_pools():
    content_items = [{"key": f"k{i}", "title": "T", "body_html": "x", "links": []} for i in range(45)]
    plan, _ = build_plan([], {}, 1, {}, {}, {}, content_items=content_items)
    valid_slots = set(INDEX_SLOTS) | set(HEAD_SPARE) | set(DIVIDER_SLOTS) | set(MID_SPARE) | set(TAIL_SPARE) | set(POST_LIBRARY_SLOTS)
    for slot, _, body in plan:
        if "<b>T</b>\n\nx" in body:
            assert slot in valid_slots


def test_link_text_not_found_hard_fails():
    item = {"key": "x", "title": "T", "body_html": "hello", "links": [{"text": "missing", "lesson": "001"}]}
    from remodel_head import resolve_content_body
    with pytest.raises(SystemExit):
        resolve_content_body(item, {"001": 100}, 1)


def test_link_lesson_with_no_message_id_hard_fails():
    item = {"key": "x", "title": "T", "body_html": "hello", "links": [{"text": "hello", "lesson": "001"}]}
    from remodel_head import resolve_content_body
    with pytest.raises(SystemExit):
        resolve_content_body(item, {}, 1)
