"""Batching the transcripts by section, the shape a skill actually takes."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "knowledge"))

from distill_batches import (
    DEFAULT_SKIP,
    group_sections,
    slugify,
    split_batches,
)

VIDEOS = [
    {"index": "001", "course": "Course A", "section": "Course Intro"},
    {"index": "002", "course": "Course A", "section": "Colour & Grading"},
    {"index": "003", "course": "Course A", "section": "Colour & Grading"},
    {"index": "004", "course": "Course B", "section": "Audio"},
    {"index": "005", "course": "Course A", "section": "Colour & Grading"},
]


def test_admin_sections_produce_no_batch():
    sections = group_sections(VIDEOS, DEFAULT_SKIP)
    assert all(s != "Course Intro" for _c, s, _i in sections)


def test_lessons_regroup_under_their_section_across_courses():
    assert group_sections(VIDEOS, DEFAULT_SKIP) == [
        ("Course A", "Colour & Grading", ["002", "003", "005"]),
        ("Course B", "Audio", ["004"]),
    ]


def test_slug_is_filename_safe():
    assert slugify("Video Gear You DO & DON'T Need!") == "video-gear-you-do-don-t-need"
    assert slugify("") == "section"


def test_a_section_that_fits_stays_one_batch():
    texts = {"002": "x" * 10, "003": "x" * 10}
    assert split_batches(["002", "003"], texts, 100) == [["002", "003"]]


def test_an_oversized_section_splits():
    texts = {"a": "x" * 60, "b": "x" * 60, "c": "x" * 10}
    assert split_batches(["a", "b", "c"], texts, 100) == [["a"], ["b", "c"]]


def test_a_single_oversized_lesson_is_still_emitted():
    texts = {"a": "x" * 500}
    assert split_batches(["a"], texts, 100) == [["a"]]
