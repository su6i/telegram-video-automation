import pytest

from src.index_builder import UNBOUNDED, build_index, build_index_or_fail, visible


def test_title_carries_link_not_number():
    entries = [("Course A", "Section 1", "001", "Intro")]
    msg_of = {"001": 100}
    attach_state = {}
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state)
    post = posts[0]
    
    # 1. Assert the raw string >{num}</a> never appears
    assert "001</a>" not in post
    assert '<a href="https://t.me/c/1/100">001<' not in post
    
    # 2. Assert title text is wrapped
    assert '<a href="https://t.me/c/1/100">Intro</a>' in post

def test_bottom_index_config_excludes_resources():
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 4)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 4)}
    attach_state = {
        f"{i:03d}": {"pack_parts": {"1": 2000 + i}, "subtitle": 3000 + i}
        for i in range(1, 4)
    }
    
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state, include_resource=False, include_subtitle=True)
    post = posts[0]
    
    # Every post contains CC
    assert post.count("CC") == 3
    # Glyph 📎 never appears
    assert "📎" not in post
    # No link points at a resource ID
    assert "2001" not in post
    assert "2002" not in post
    assert "2003" not in post

def test_entity_cap_and_utf16_cap_hold_without_resources():
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 111)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 111)}
    attach_state = {
        f"{i:03d}": {"pack_parts": {"1": 2000 + i}, "subtitle": 3000 + i}
        for i in range(1, 111)
    }
    
    posts = build_index(entries, msg_of, internal=1, attach_state=attach_state, include_resource=False, include_subtitle=True)
    
    assert len(posts) > 1
    for post in posts:
        ent_count = post.count("<a ") + post.count("<b>")
        assert ent_count <= 100
        
        # Check UTF-16 char length
        utf16_len = len(visible(post).encode("utf-16-le")) // 2
        assert utf16_len <= 4096

def test_build_index_or_fail_hard_fails():
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 111)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 111)}
    attach_state = {}
    
    # Normally this takes ~2-3 posts
    available_slots = 1
    
    with pytest.raises(SystemExit) as exc:
        build_index_or_fail(entries, msg_of, internal=1, attach_state=attach_state, available_slots=available_slots, caller="test-caller")
    
    msg = str(exc.value)
    assert "test-caller" in msg
    assert "index needs" in msg
    # The required number should be in the message
    assert "but only 1 slots exist" in msg

def test_build_index_or_fail_unbounded_does_not_raise():
    entries = [("Course A", "Section 1", f"{i:03d}", "X") for i in range(1, 111)]
    msg_of = {f"{i:03d}": 1000 + i for i in range(1, 111)}
    attach_state = {
        f"{i:03d}": {"pack_parts": {"1": 2000 + i}, "subtitle": 3000 + i}
        for i in range(1, 111)
    }
    
    posts_direct = build_index(entries, msg_of, internal=1, attach_state=attach_state)
    posts_unbounded = build_index_or_fail(
        entries, msg_of, internal=1, attach_state=attach_state,
        available_slots=UNBOUNDED, caller="test-caller"
    )
    
    assert posts_direct == posts_unbounded
    assert len(posts_unbounded) > 1
