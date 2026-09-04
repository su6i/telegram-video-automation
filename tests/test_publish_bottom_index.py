import json
import types
from unittest.mock import AsyncMock, patch

import pytest
from pyrogram.errors import FloodWait

from tools.channel.publish_bottom_index import (
    DEFAULT_STATE_IDS,
    build_bottom_index_posts,
    delete_old_index,
    ids_to_delete,
    load_state,
    move_pin,
    post_new_index,
    post_report,
    republish_bottom_index,
    save_state,
)


def test_load_state_seeds_default_on_first_run(tmp_path):
    state_file = tmp_path / "bottom_index_state.json"
    state = load_state(state_file)
    assert state == {"ids": [685, 686, 687, 688, 689, 690, 691], "pinned": None}


def test_load_state_reads_existing(tmp_path):
    state_file = tmp_path / "bottom_index_state.json"
    data = {"ids": [900, 901], "pinned": 900}
    state_file.write_text(json.dumps(data))
    state = load_state(state_file)
    assert state == data


def test_save_state_roundtrip(tmp_path):
    state_file = tmp_path / "bottom_index_state.json"
    save_state(state_file, [1000, 1001], 1000)
    data = json.loads(state_file.read_text())
    assert data == {"ids": [1000, 1001], "pinned": 1000}


def test_ids_to_delete_filters_protected_ids():
    assert ids_to_delete([685, 900, 691, 901]) == [900, 901]


@pytest.mark.asyncio
async def test_post_new_index_sends_silently():
    app = AsyncMock()
    app.send_message.side_effect = [
        types.SimpleNamespace(id=1000),
        types.SimpleNamespace(id=1001),
    ]
    posts = ["post1", "post2"]
    
    new_ids = await post_new_index(app, 123, posts)
    
    assert new_ids == [1000, 1001]
    assert app.send_message.call_count == 2
    for call in app.send_message.call_args_list:
        assert call.kwargs.get("disable_notification") is True


@pytest.mark.asyncio
async def test_republish_posting_failure_deletes_and_pins_nothing():
    app = AsyncMock()
    app.send_message.side_effect = [
        types.SimpleNamespace(id=1000),
        types.SimpleNamespace(id=1001),
        Exception("Post failed"),
    ]
    posts = ["post1", "post2", "post3"]
    old_ids = [900, 901]
    
    with pytest.raises(Exception, match="Post failed"):
        await republish_bottom_index(app, 123, posts, old_ids, 900)
        
    app.delete_messages.assert_not_called()
    app.pin_chat_message.assert_not_called()


@pytest.mark.asyncio
async def test_republish_delete_failure_leaves_new_posts_sent_and_pin_unmoved():
    app = AsyncMock()
    app.send_message.side_effect = [
        types.SimpleNamespace(id=1000),
        types.SimpleNamespace(id=1001),
    ]
    app.delete_messages.side_effect = Exception("Delete failed")
    posts = ["post1", "post2"]
    old_ids = [900, 901]
    
    with pytest.raises(Exception, match="Delete failed"):
        await republish_bottom_index(app, 123, posts, old_ids, 900)
        
    assert app.send_message.call_count == len(posts)
    app.pin_chat_message.assert_not_called()


@pytest.mark.asyncio
async def test_republish_protected_ids_are_never_deleted():
    app = AsyncMock()
    app.send_message.side_effect = [
        types.SimpleNamespace(id=1000),
    ]
    posts = ["post1"]
    old_ids = DEFAULT_STATE_IDS
    
    await republish_bottom_index(app, 123, posts, old_ids, None)
    
    app.delete_messages.assert_not_called()
    app.send_message.assert_called_once()
    app.pin_chat_message.assert_called_once()


@pytest.mark.asyncio
async def test_delete_old_index_noop_when_empty():
    app = AsyncMock()
    await delete_old_index(app, 123, [])
    app.delete_messages.assert_not_called()


@pytest.mark.asyncio
async def test_move_pin_pins_new_and_unpins_old():
    app = AsyncMock()
    await move_pin(app, 123, 1000, 900)
    app.pin_chat_message.assert_called_once_with(123, 1000, disable_notification=True)
    app.unpin_chat_message.assert_called_once_with(123, 900)


@pytest.mark.asyncio
async def test_move_pin_skips_unpin_when_no_prior_pin():
    app = AsyncMock()
    await move_pin(app, 123, 1000, None)
    app.pin_chat_message.assert_called_once_with(123, 1000, disable_notification=True)
    app.unpin_chat_message.assert_not_called()


@pytest.mark.asyncio
@patch("tools.channel.publish_bottom_index.asyncio.sleep", new_callable=AsyncMock)
async def test_post_new_index_retries_on_floodwait(mock_sleep):
    app = AsyncMock()
    app.send_message.side_effect = [
        FloodWait(value=0),
        types.SimpleNamespace(id=1000),
    ]
    posts = ["post1"]
    
    new_ids = await post_new_index(app, 123, posts)
    
    assert new_ids == [1000]
    assert app.send_message.call_count == 2
    mock_sleep.assert_called_once()


def test_post_report_counts_chars_and_entities():
    entries = [("Course A", "Section 1", "001", "Intro")]
    msg_of = {"001": 100}
    attach_state = {
        "001": {"pack_parts": {"1": 200}, "duplicate_note": None, "subtitle": 201},
    }
    posts = build_bottom_index_posts(entries, msg_of, internal=1, attach_state=attach_state)
    
    report = post_report(posts)
    assert len(report) == 1
    r = report[0]
    assert r["post"] == 1
    assert r["chars"] > 0
    # title link + 📎 resource link + CC subtitle link + <b>course</b> header
    # + <b>section</b> header (both headers fire since this is the first
    # entry) = 5 entities.
    assert r["entities"] == 5
