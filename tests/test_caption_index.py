"""The channel carries two caption generations; both must yield an index."""
import pytest

from src.caption_index import extract_index_and_title, safe_extract_number

OLD_STYLE = "‏001 - - AI Creator Course Course Intro 001 - Welcome! Course Overview"
NEW_STYLE = (
    "Weekend Youtuber\n"
    "DISCOUNTS | Saving you MONEY!\n"
    "283 - Save 20% on Timebolt AI Tools\n\n"
    "\U0001f4dd Info:\nTO PURCHASE TIMEBOLT!"
)
BOLD_STYLE = "AI Creator Course\nAI Video Creation\n**036 - How to create consistent characters**"


@pytest.mark.parametrize(
    "caption, expected",
    [
        (OLD_STYLE, (1, "Welcome! Course Overview")),
        (NEW_STYLE, (283, "Save 20% on Timebolt AI Tools")),
        (BOLD_STYLE, (36, "How to create consistent characters")),
    ],
)
def test_index_is_read_from_any_header_line(caption, expected):
    assert extract_index_and_title(caption) == expected


def test_a_body_line_is_not_mistaken_for_the_index():
    caption = "Weekend Youtuber\nDISCOUNTS\nGear list\n\n2026 - the year of AI"
    assert extract_index_and_title(caption) == (None, "")


def test_no_caption_yields_no_index():
    assert extract_index_and_title("") == (None, "")
    assert extract_index_and_title(None) == (None, "")


@pytest.mark.parametrize(
    "name, expected",
    [
        ("001_Welcome! Course Overview_1080p_crf23", 1),
        ("080_HOW TO USE LUTS", 80),
        ("[156] Some Title", 156),
        ("no number here", 999999),
    ],
)
def test_filenames_still_sort(name, expected):
    assert safe_extract_number(name) == expected


def test_unnumbered_caption_sorts_last():
    assert safe_extract_number("Weekend Youtuber\nDISCOUNTS\nGear list") == 999999


def _video(mid, caption):
    return {"message_id": mid, "caption": caption, "date": None}


def test_a_reuploaded_lesson_appears_once_in_the_index():
    import importlib.util
    from pathlib import Path as P

    spec = importlib.util.spec_from_file_location(
        "_uc", P(__file__).resolve().parents[1] / "scripts" / "update_captions.py")
    # The module needs .env credentials at import time, so pull the helper out
    # of the source instead of importing the whole script.
    src = spec.origin
    text = open(src, encoding="utf-8").read()
    start = text.index("def dedupe_by_lesson(")
    end = text.index("def plan_from_existing(")
    ns = {"safe_extract_number": safe_extract_number}
    exec(text[start:end], ns)
    dedupe = ns["dedupe_by_lesson"]

    videos = [
        _video(306, "AI Creator Course\nCourse Intro\n001 - Welcome"),
        _video(65, "001 - Welcome"),
        _video(400, "AI Creator Course\nCourse Intro\n002 - Community"),
        _video(999, "no lesson number anywhere"),
    ]
    kept = sorted(v["message_id"] for v in dedupe(videos))
    assert kept == [306, 400]
