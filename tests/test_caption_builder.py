"""Regression tests for the defects found in the 2026-08 1080p batch."""
import pytest

from src.caption_builder import build_caption, unfragment_text, validate_caption

META = {
    "course": "Example Course",
    "section": "Example Section",
    "index": "013",
    "total": "50",
    "line_title": "Example Lesson",
    "url": "https://example.test/lesson",
}


def test_links_survive_underscore_escaping():
    """The link sentinel used to be mangled into MARKDOWN\\_LINK\\_PLACEHOLDER\\_0."""
    out = validate_caption("• [Fal model](https://fal.ai/models/fal-ai/flux_pro)")
    assert out == "• [Fal model](https://fal.ai/models/fal-ai/flux_pro)"
    assert "PLACEHOLDER" not in out


def test_bullet_and_trailing_punctuation_are_rejoined():
    raw = "•\nFrom the pop-up menu, select\nSettings\n.\n•\nIn Settings, click\nPersonalization\n."
    assert unfragment_text(raw) == (
        "• From the pop-up menu, select Settings.\n"
        "• In Settings, click Personalization."
    )


def test_shouted_header_torn_in_two_is_rejoined():
    assert unfragment_text("IMPORTANT\nNOTE:\nUse good photos.") == (
        "IMPORTANT NOTE:\nUse good photos."
    )


def test_a_following_line_is_not_swallowed_by_an_all_caps_line():
    raw = "CLICK HERE\nAccess nano banana through fal.ai:"
    assert unfragment_text(raw) == raw


def test_link_anchor_keeps_its_bullet_out_of_the_anchor_text():
    extra = {
        "description": "• Sony ZV-e10 CAMERA:\nGreat starter camera.",
        "links": [{"text": "• Sony ZV-e10 CAMERA", "url": "https://amzn.to/4abXKOo"}],
    }
    caption, _ = build_caption(META, extra, "fallback")
    assert "• [Sony ZV-e10 CAMERA](https://amzn.to/4abXKOo)" in caption
    assert "[• Sony" not in caption
    assert "🔗 **Links:**" not in caption  # inlined, not dumped into a header


def test_short_anchor_is_not_nested_inside_a_longer_one():
    extra = {
        "description": "• Go to the FLUX LORA PORTRAIT TRAINER on Fal.ai",
        "links": [
            {"text": "FLUX LORA", "url": "https://fal.ai/models/fal-ai/flux-lora"},
            {"text": "Go to the FLUX LORA PORTRAIT TRAINER on Fal.ai",
             "url": "https://fal.ai/models/fal-ai/flux-lora-portrait-trainer"},
        ],
    }
    caption, overflow = build_caption(META, extra, "fallback")
    assert "[[" not in caption + overflow
    assert "](https://fal.ai/models/fal-ai/flux-lora)P" not in caption + overflow


def test_caption_never_exceeds_the_limit_and_keeps_markdown_intact():
    extra = {
        "description": "**Chapter**\n" + "Long sentence about editing. " * 120,
        "links": [{"text": f"Gear item {i}", "url": f"https://amzn.to/{i}"} for i in range(20)],
    }
    caption, overflow = build_caption(META, extra, "fallback")
    assert len(caption) <= 1024
    assert caption.count("**") % 2 == 0
    assert caption.count("[") == caption.count("]")
    assert overflow  # nothing is silently dropped


def test_scraped_script_artifacts_are_stripped():
    extra = {"description": "Real text.\n// <![CDATA[\nvar x = 1;\n// ]]>", "links": []}
    caption, _ = build_caption(META, extra, "fallback")
    assert "CDATA" not in caption
    assert "Real text." in caption


@pytest.mark.parametrize("bad", ["\x00", "\x01", "\x02", "@@@"])
def test_no_internal_sentinel_reaches_the_caption(bad):
    extra = {
        "description": "IMPORTANT\nNOTE:\nCheck the link\nCLICK HERE",
        "links": [{"text": "Check the link: CLICK HERE", "url": "https://example.test/x"}],
    }
    caption, overflow = build_caption(META, extra, "fallback")
    assert bad not in caption + overflow
