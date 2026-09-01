import json
import types

from tools.channel.purge_superseded import (
    filter_video_candidates,
    parse_dup_range,
    prepare_purge_plan,
    write_backup,
)


def test_parse_dup_range():
    ids = parse_dup_range("65-109,126-237")
    assert 65 in ids
    assert 109 in ids
    assert 126 in ids
    assert 237 in ids
    assert 110 not in ids
    assert 125 not in ids
    assert len(ids) == (109 - 65 + 1) + (237 - 126 + 1)


def test_filter_video_candidates():
    m1 = types.SimpleNamespace(id=1, video=True, empty=False, caption="first")
    m2 = types.SimpleNamespace(id=2, video=False, empty=False, caption="second")
    m3 = types.SimpleNamespace(id=3, video=True, empty=True, caption="third")
    m4 = None

    candidates = filter_video_candidates([m1, m2, m3, m4])
    assert len(candidates) == 1
    assert candidates[0].id == 1


def test_write_backup(tmp_path):
    out_file = tmp_path / "backup.json"
    records = {"123": {"caption": "foo", "matched_title": "bar"}}
    write_backup(str(out_file), records)

    with open(out_file, encoding="utf-8") as f:
        data = json.load(f)

    assert data == records


def test_prepare_purge_plan_dry_run():
    m1 = types.SimpleNamespace(id=100, caption="001 - Title 1", video=True, empty=False)
    m2 = types.SimpleNamespace(
        id=101, caption="002 - Title 2\nhttps://t.me/c/123/456", video=True, empty=False
    )

    live_by_title = {"Title 1"}

    target_ids, backup_records, report = prepare_purge_plan(
        [m1, m2], live_by_title, 123
    )

    assert target_ids == [100, 101]
    assert backup_records["100"]["matched_title"] == "Title 1"
    assert backup_records["101"]["matched_title"] is None

    assert "yes" not in report[0]
    assert "yes" in report[1]
