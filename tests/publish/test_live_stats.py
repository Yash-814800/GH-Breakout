from datetime import date, datetime

from breakout.publish import live_stats as ls


def test_record_snapshot_replaces_same_day_and_prunes():
    h = ls.record_snapshot({}, date(2026, 8, 1), {1: 10})
    h = ls.record_snapshot(h, date(2026, 10, 20), {1: 50, 2: 7})
    h = ls.record_snapshot(h, date(2026, 10, 20), {1: 51})
    assert "2026-08-01" not in h
    assert h["2026-10-20"] == {"1": 51, "2": 7}


def test_star_gain_uses_oldest_snapshot_in_window():
    h = {"2026-10-13": {"1": 100}, "2026-10-17": {"1": 400}, "2026-10-20": {"1": 700}}
    assert ls.star_gain(h, 1, date(2026, 10, 20)) == (600, 7)
    assert ls.star_gain(h, 2, date(2026, 10, 20)) == (None, None)
    assert ls.star_gain({"2026-10-20": {"1": 5}}, 1, date(2026, 10, 20)) == (None, None)


def test_star_gain_never_negative():
    h = {"2026-10-19": {"1": 100}, "2026-10-20": {"1": 90}}
    assert ls.star_gain(h, 1, date(2026, 10, 20)) == (0, 1)


def test_snapshots_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    assert ls.load_snapshots(p) == {}
    ls.save_snapshots(p, {"2026-10-20": {"1": 5}})
    assert ls.load_snapshots(p) == {"2026-10-20": {"1": 5}}


def test_age_days():
    assert ls.age_days(datetime(2026, 10, 6, 21, 48), date(2026, 10, 20)) == 13
    assert ls.age_days(None, date(2026, 10, 20)) is None
    assert ls.age_days(datetime(2026, 10, 21), date(2026, 10, 20)) == 0


def test_fetch_live_info_without_token(monkeypatch):
    monkeypatch.delenv("GH_ENRICH_TOKEN", raising=False)
    assert ls.fetch_live_info(None, [1, 2]) == {}
