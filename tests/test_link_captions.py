"""The caption link has to survive a re-run and a caption near the limit."""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "knowledge"))

from link_captions import (  # noqa: E402
    CAPTION_LIMIT,
    RESOURCES_LABEL,
    RESOURCES_LABEL_SHORT,
    SUBTITLES_LABEL,
    choose_target,
    fit_caption,
    internal_chat_id,
    plan_edits,
)

CANONICAL = {"role": "canonical", "pack_parts": {"2": 702, "1": 701}, "subtitle": 703}
DUPLICATE = {"role": "duplicate", "pack_parts": {}, "duplicate_note": 710, "subtitle": 711}
SUBS_ONLY = {"role": "subtitle-only", "pack_parts": {}, "duplicate_note": None, "subtitle": 720}
NOTHING = {"role": "canonical", "pack_parts": {}, "duplicate_note": None, "subtitle": None}


def test_the_first_pack_part_wins_over_the_subtitle():
    assert choose_target(CANONICAL) == (701, RESOURCES_LABEL)


def test_a_duplicate_points_at_its_note():
    assert choose_target(DUPLICATE) == (710, RESOURCES_LABEL)


def test_a_subtitle_only_lesson_points_at_the_subtitle():
    assert choose_target(SUBS_ONLY) == (720, SUBTITLES_LABEL)


def test_a_lesson_with_nothing_sent_is_not_linked():
    assert choose_target(NOTHING) is None
    assert choose_target({}) is None
    assert choose_target(None) is None


def test_only_mapped_lessons_are_planned():
    state = {"080": CANONICAL, "081": SUBS_ONLY, "082": NOTHING}
    plan = plan_edits(state, {"080": 500, "082": 502})
    assert plan == [("080", 500, 701, RESOURCES_LABEL)]


def test_internal_id_needs_the_minus_100_form():
    assert internal_chat_id("-1001234567890") == "1234567890"
    assert internal_chat_id("@somechannel") is None
    assert internal_chat_id(None) is None


def test_a_short_caption_takes_the_full_label():
    html, length = fit_caption("<b>080 - Title</b>", "080 - Title", "123", 701, RESOURCES_LABEL)
    assert html.endswith('<a href="https://t.me/c/123/701">📎 Resources &amp; subtitles</a>'
                         .replace("&amp;", "&"))
    assert length == len("080 - Title") + len(f"\n\n{RESOURCES_LABEL}")


def test_a_caption_near_the_limit_falls_back_to_the_short_label():
    text = "x" * (CAPTION_LIMIT - len(f"\n\n{RESOURCES_LABEL_SHORT}"))
    fitted = fit_caption(text, text, "123", 701, RESOURCES_LABEL)
    assert fitted is not None
    assert RESOURCES_LABEL_SHORT in fitted[0]
    assert fitted[1] == CAPTION_LIMIT


def test_a_caption_at_the_limit_is_left_alone():
    text = "x" * CAPTION_LIMIT
    assert fit_caption(text, text, "123", 701, RESOURCES_LABEL) is None
