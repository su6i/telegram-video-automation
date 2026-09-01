"""The guard that keeps someone else's expression out of a public repo."""
import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "tools" / "knowledge"))

from check_skill_leak import (
    build_banned,
    corpus_ngrams,
    find_banned,
    find_overlap,
    manifest_terms,
    normalize,
    strip_markdown,
    transcript_titles,
)

MANIFEST = """# Index | Title | URL
# === Some Branded Course ===

## --- Editing Fundamentals ---
001_Colour Grading Basics | https://a
002 | Audio Sweetening | https://b
"""

TRANSCRIPT = {
    "index": "001",
    "title": "Colour Grading Basics",
    "text": "the very first thing you want to do is drop a curve on the clip and "
            "pull the shadows down until the blacks feel right",
}


@pytest.fixture
def corpus(tmp_path):
    manifest = tmp_path / "downloaded_video.txt"
    manifest.write_text(MANIFEST, encoding="utf-8")
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    (tdir / "001_Colour Grading Basics.json").write_text(
        json.dumps(TRANSCRIPT), encoding="utf-8")
    return manifest, tdir


def test_course_section_and_lesson_titles_all_become_terms(corpus):
    manifest, _ = corpus
    assert manifest_terms(str(manifest)) == {
        "Some Branded Course", "Editing Fundamentals",
        "Colour Grading Basics", "Audio Sweetening",
    }


def test_titles_are_also_read_from_the_transcripts(corpus):
    _, tdir = corpus
    assert transcript_titles(tdir) == {"Colour Grading Basics"}


def test_generic_single_words_are_not_banned():
    banned = build_banned({"Course", "Intro", "Wistia", "Some Branded Course"})
    assert "some branded course" in banned
    assert "wistia" in banned
    assert "course" not in banned
    assert "intro" not in banned


def test_an_extra_terms_file_is_merged(tmp_path):
    extra = tmp_path / "extra.txt"
    extra.write_text("Jane Instructor\n# a comment\n\nsomesite.com\n", encoding="utf-8")
    banned = build_banned(set(), str(extra))
    assert banned == {"jane instructor", "somesite com"}


def test_a_branded_name_in_the_skill_is_caught(corpus):
    manifest, tdir = corpus
    banned = build_banned(manifest_terms(str(manifest)) | transcript_titles(tdir))
    text = "Grade in three passes, as taught in Some Branded Course."
    assert "some branded course" in find_banned(text, banned)


def test_our_own_words_pass(corpus):
    manifest, tdir = corpus
    banned = build_banned(manifest_terms(str(manifest)) | transcript_titles(tdir))
    text = "Grade in three passes: contrast, balance, then look."
    assert find_banned(text, banned) == []


def test_a_copied_sentence_is_caught(corpus):
    _, tdir = corpus
    grams = corpus_ngrams(tdir, 8)
    text = "Remember: the very first thing you want to do is drop a curve on the clip."
    assert find_overlap(text, grams, 8)


def test_a_paraphrase_passes(corpus):
    _, tdir = corpus
    grams = corpus_ngrams(tdir, 8)
    text = "Start with a curve adjustment, then bring the shadows down to taste."
    assert find_overlap(text, grams, 8) == []


def test_code_blocks_are_not_scanned(corpus):
    manifest, tdir = corpus
    banned = build_banned(manifest_terms(str(manifest)) | transcript_titles(tdir))
    text = "Run this:\n```\n# Some Branded Course\n```\nand move on."
    assert find_banned(text, banned) == []


def test_normalisation_survives_case_accents_and_punctuation():
    assert normalize("Côlour-Grading, BASICS!") == "colour grading basics"


def test_strip_markdown_removes_inline_code():
    assert "secret" not in strip_markdown("use `secret` here")
