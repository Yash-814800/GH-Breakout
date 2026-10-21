"""Unit tests for Phase 12 distribution: feed items, badges, weekly digest, Discussions."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

from breakout.config import get_config
from breakout.publish import distribution as dist


def _snapshot(root: Path, d: date, rows: list[tuple[int, str, float, str | None]]) -> None:
    """rows = (repo_id, name, prob, explanation), already in rank order."""
    df = pd.DataFrame(
        {
            "snapshot_date": d.isoformat(),
            "repo_id": [r[0] for r in rows],
            "repo_name": [r[1] for r in rows],
            "rank": range(1, len(rows) + 1),
            "prob": [r[2] for r in rows],
            "explanation": [r[3] for r in rows],
            "model_version": "m1",
            "suspicion_score": [None] * len(rows),
        }
    )
    p = root / "snapshots" / "predictions" / f"date={d}" / "predictions.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = get_config(None)
    monkeypatch.setattr(cfg.site, "leaderboard_size", 3, raising=False)
    monkeypatch.setattr(dist, "SNAP_PRED", tmp_path / "snapshots" / "predictions")
    monkeypatch.setattr(dist, "SNAP_OUT", tmp_path / "snapshots" / "outcomes")
    monkeypatch.setattr(dist, "DATA_DIR", tmp_path / "pub" / "data")
    monkeypatch.setattr(dist, "BADGES_DIR", tmp_path / "pub" / "badges")
    monkeypatch.setattr(dist, "DIGESTS_DIR", tmp_path / "pub" / "data" / "digests")
    monkeypatch.setattr(dist, "FEED_ITEMS_JSON", tmp_path / "pub" / "data" / "feed_items.json")
    monkeypatch.setattr(dist, "_hidden", lambda: (set(), {"hidden/repo"}))
    monkeypatch.setattr(dist.ledger, "LEDGER_PATH", tmp_path / "ledger.csv")
    return cfg, tmp_path


def test_new_entry_needs_30_days_away(env):
    cfg, root = env
    d0 = date(2026, 1, 1)
    _snapshot(root, d0, [(1, "a/one", 0.3, "x"), (2, "b/two", 0.2, None)])
    _snapshot(root, d0 + timedelta(days=1), [(2, "b/two", 0.2, None), (3, "c/three", 0.1, None)])
    # repo 1 returns exactly 30 days after its last sighting, repo 2 after 31: both are new
    _snapshot(root, d0 + timedelta(days=30), [(1, "a/one", 0.3, "x")])
    _snapshot(root, d0 + timedelta(days=32), [(2, "b/two", 0.2, None)])
    got = [(e["repo_id"], e["date"]) for e in dist.new_entries(dist.load_board(cfg))]
    assert (1, "2026-01-01") in got and (3, "2026-01-02") in got
    assert (1, "2026-01-31") in got
    assert (2, "2026-02-02") in got


def test_entry_window_boundary(env):
    cfg, root = env
    d0 = date(2026, 1, 1)
    _snapshot(root, d0, [(1, "a/one", 0.3, None)])
    _snapshot(root, d0 + timedelta(days=29), [(1, "a/one", 0.3, None)])
    _snapshot(root, d0 + timedelta(days=58), [(1, "a/one", 0.3, None)])
    got = [e["date"] for e in dist.new_entries(dist.load_board(cfg))]
    assert got == ["2026-01-01"]  # a sighting every <30 days keeps the repo "on the board"


def test_hidden_repos_never_enter_feed_or_badges(env):
    cfg, root = env
    _snapshot(root, date(2026, 1, 1), [(1, "hidden/repo", 0.9, None), (2, "ok/repo", 0.5, None)])
    assert [e["repo_id"] for e in dist.new_entries(dist.load_board(cfg))] == [2]
    assert set(dist.build_badges(cfg)) == {2}


def test_feed_items_order_guid_and_limit(env):
    cfg, root = env
    d0 = date(2026, 1, 1)
    for i in range(3):
        _snapshot(root, d0 + timedelta(days=i), [(10 + i, f"o/r{i}", 0.2 + i / 10, f"why {i}")])
    items = dist.build_feed_items(cfg)
    assert [i["guid"] for i in items] == ["12:2026-01-03", "11:2026-01-02", "10:2026-01-01"]
    assert items[0]["explanation"] == "why 2"
    assert items[0]["suspicion_note"] is None
    # earlier items keep their stored facts; unknown ones are kept too
    prev = [
        {**items[2], "age_days": 7},
        {**items[2], "guid": "99:2025-01-01", "date": "2025-01-01"},
    ]
    again = dist.build_feed_items(cfg, previous=prev)
    assert next(i for i in again if i["guid"] == "10:2026-01-01")["age_days"] == 7
    assert any(i["guid"] == "99:2025-01-01" for i in again)


def test_feed_is_capped_at_100(env):
    cfg, root = env
    prev = [
        {"guid": f"{i}:2025-01-01", "repo_id": i, "date": "2025-01-01", "rank": 1}
        for i in range(150)
    ]
    assert len(dist.build_feed_items(cfg, previous=prev)) == dist.FEED_LIMIT


def test_badges_today_vs_flagged_and_never_suspicion(env):
    cfg, root = env
    d1, d2 = date(2026, 3, 1), date(2026, 3, 5)
    _snapshot(root, d1, [(1, "a/old", 0.4, None), (2, "b/stay", 0.2, None)])
    _snapshot(root, d2, [(2, "b/stay", 0.34, None), (3, "c/new", 0.05, None)])
    b = dist.build_badges(cfg)
    assert b[2]["payload"] == {
        "schemaVersion": 1,
        "label": "breakout radar",
        "message": "#1 today · 34%",
        "color": dist.badge_colour(0.34),
    }
    assert b[1]["payload"]["message"] == "flagged 2026-03-01"
    assert b[1]["payload"]["color"] == dist.BADGE_NEUTRAL
    assert all("suspicion" not in json.dumps(v["payload"]).lower() for v in b.values())


def test_badges_outside_90_days_are_dropped(env):
    cfg, root = env
    _snapshot(root, date(2026, 1, 1), [(1, "a/old", 0.4, None)])
    _snapshot(root, date(2026, 6, 1), [(2, "b/new", 0.2, None)])
    assert set(dist.build_badges(cfg)) == {2}


def test_export_badges_writes_id_and_by_name_and_cleans(env):
    cfg, root = env
    _snapshot(
        root, date(2026, 3, 1), [(1, "Owner/Repo.js", 0.4, None), (2, "repo_id=2", 0.2, None)]
    )
    files = dist.export_badges(cfg)
    assert (dist.BADGES_DIR / "1.json").exists()
    by_name = dist.BADGES_DIR / "by-name" / "owner" / "repo.js.json"
    assert by_name.exists()
    assert json.loads(by_name.read_text())["schemaVersion"] == 1
    assert (dist.BADGES_DIR / "2.json").exists()  # no by-name file for a placeholder name
    assert len(files) == 3
    stale = dist.BADGES_DIR / "999.json"
    stale.write_text("{}")
    dist.export_badges(cfg)
    assert not stale.exists()


def test_name_parts_rejects_unsafe_names():
    assert dist._name_parts("a/b") == ("a", "b")
    assert dist._name_parts("repo_id=5") is None
    assert dist._name_parts("../x") is None
    assert dist._name_parts("a/b/c") is None
    assert dist._name_parts("a b/c") is None


def test_badge_markdown_has_encoded_endpoint_url():
    md = dist.badge_markdown(42)
    img = md[md.index("(") + 1 : md.index(")")]
    assert img.startswith("https://img.shields.io/endpoint?url=")
    target = parse_qs(urlparse(img).query)["url"][0]
    assert target == f"{dist.SITE_URL}/badges/42.json"
    assert md.endswith(f"({dist.SITE_URL}/repo/42/)")


def test_weeks():
    assert dist.parse_week("2026-W43") == (date(2026, 10, 19), date(2026, 10, 25))
    assert dist.iso_week(date(2026, 10, 21)) == "2026-W43"
    assert dist.default_week(date(2026, 10, 25)) == "2026-W43"  # a Sunday: the week ending today
    assert dist.default_week(date(2026, 10, 21)) == "2026-W42"  # mid-week: the last complete week
    with pytest.raises(ValueError):
        dist.parse_week("2026-43")


def _outcomes(root: Path, d: date, rows: list[tuple[int, int, float]]) -> None:
    p = root / "snapshots" / "outcomes" / f"date={d}" / "outcomes.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "repo_id": [r[0] for r in rows],
            "label": [r[1] for r in rows],
            "gain_30d": [r[2] for r in rows],
        }
    ).to_parquet(p)


def test_digest_sections_and_honest_misses(env, monkeypatch):
    cfg, root = env
    monkeypatch.setattr(dist, "_model_notes", lambda s, e: ["note a"])
    monkeypatch.setattr(dist, "_drift_notes", lambda s, e: [])
    start, _ = dist.parse_week("2026-W43")
    old = start - timedelta(days=30)
    _snapshot(root, old, [(7, "h/hit", 0.4, None), (8, "m/miss", 0.3, None)])
    _outcomes(root, old, [(7, 1, 900.0), (8, 0, 3.0)])
    p = root / "snapshots" / "predictions"
    _snapshot(
        root, start, [(2, "b/two", 0.2, "e2"), (3, "c/three", 0.1, None), (4, "d/four", 0.05, None)]
    )
    # repo 1 climbs from rank 30 (not on the board) to rank 1 during the week
    _snapshot(root, start + timedelta(days=2), [(1, "a/one", 0.5, "e1"), (2, "b/two", 0.2, None)])
    # rewrite the first snapshot with a deep rank for repo 1
    first = pd.read_parquet(p / f"date={start}" / "predictions.parquet")
    extra = first.iloc[[0]].copy()
    extra["repo_id"], extra["repo_name"], extra["rank"] = 1, "a/one", 30
    pd.concat([first, extra]).to_parquet(p / f"date={start}" / "predictions.parquet")
    doc = dist.build_digest(cfg, "2026-W43")
    assert doc["week"] == "2026-W43" and doc["start"] == "2026-10-19" and doc["end"] == "2026-10-25"
    assert {r["repo_id"] for r in doc["new_on_board"]} == {1, 2, 3, 4}
    assert doc["new_on_board"][0]["repo_id"] == 1  # highest probability first
    assert [m["repo_id"] for m in doc["movers"]] == [1]
    assert doc["movers"][0]["from_rank"] == 30 and doc["movers"][0]["to_rank"] == 1
    assert {(r["repo_id"], r["hit"]) for r in doc["matured"]} == {(7, True), (8, False)}
    assert "1 of 2 matured predictions broke out" in doc["summary"]
    assert "note a" in doc["notes"]


def test_digest_without_matured_says_so(env, monkeypatch):
    cfg, root = env
    monkeypatch.setattr(dist, "_model_notes", lambda s, e: [])
    monkeypatch.setattr(dist, "_drift_notes", lambda s, e: [])
    start, _ = dist.parse_week("2026-W43")
    _snapshot(root, start, [(2, "b/two", 0.2, None)])
    doc = dist.build_digest(cfg, "2026-W43")
    assert doc["matured"] == []
    assert "no predictions have matured yet" in doc["summary"]


def test_write_digest_builds_index_sorted(env):
    _, root = env
    for wk, summ in (("2026-W41", "a"), ("2026-W43", "c"), ("2026-W42", "b")):
        s, e = dist.parse_week(wk)
        dist.write_digest(
            {
                "week": wk,
                "start": s.isoformat(),
                "end": e.isoformat(),
                "summary": summ,
                "new_on_board": [],
                "movers": [],
                "matured": [],
                "notes": [],
            }
        )
    idx = json.loads((dist.DIGESTS_DIR / "index.json").read_text())
    assert [m["week"] for m in idx] == ["2026-W43", "2026-W42", "2026-W41"]
    assert set(idx[0]) == {"week", "start", "end", "summary"}


def test_digest_markdown_links_to_site():
    doc = {
        "week": "2026-W43",
        "start": "2026-10-19",
        "end": "2026-10-25",
        "summary": "s.",
        "new_on_board": [{"repo_id": 5, "repo_name": "a/b", "prob": 0.34}],
        "movers": [],
        "matured": [{"repo_id": 6, "repo_name": "c/d", "prob": 0.1, "hit": False}],
        "notes": ["n"],
    }
    md = dist.digest_markdown(doc)
    assert "[a/b](" + dist.SITE_URL + "/repo/5/) · 34%" in md
    assert "did not break out" in md
    assert md.rstrip().endswith("/digest/2026-W43/")


def test_discussion_dry_run_and_idempotency(monkeypatch):
    doc = {
        "week": "2026-W43",
        "start": "2026-10-19",
        "end": "2026-10-25",
        "summary": "s.",
        "new_on_board": [],
        "movers": [],
        "matured": [],
        "notes": [],
    }
    assert dist.post_discussion(doc, repo="o/r", token="", dry_run=True)["status"] == "dry_run"

    calls: list[str] = []
    repo = {
        "id": "R1",
        "hasDiscussionsEnabled": True,
        "discussionCategories": {"nodes": [{"id": "C1", "name": "Announcements"}]},
        "discussions": {"nodes": []},
    }

    def fake(token, query, variables):
        calls.append("create" if "createDiscussion" in query else "query")
        if "createDiscussion" in query:
            return {"createDiscussion": {"discussion": {"url": "https://x/1"}}}
        return {"repository": repo}

    monkeypatch.setattr(dist, "_graphql", fake)
    res = dist.post_discussion(doc, repo="o/r", token="t")
    assert res["status"] == "created" and res["category"] == "Announcements"  # Digest is missing
    repo["discussions"]["nodes"] = [{"title": "Weekly digest 2026-W43", "url": "https://x/1"}]
    again = dist.post_discussion(doc, repo="o/r", token="t")
    assert again["status"] == "exists" and calls.count("create") == 1
    repo["hasDiscussionsEnabled"] = False
    assert dist.post_discussion(doc, repo="o/r", token="t")["status"] == "discussions_disabled"


def test_first_snapshot_ever_is_not_counted_as_new_in_the_digest(env, monkeypatch):
    cfg, root = env
    monkeypatch.setattr(dist, "_model_notes", lambda s, e: [])
    monkeypatch.setattr(dist, "_drift_notes", lambda s, e: [])
    start, _ = dist.parse_week("2026-W43")
    _snapshot(root, start, [(1, "a/one", 0.5, None), (2, "b/two", 0.2, None)])
    _snapshot(root, start + timedelta(days=1), [(1, "a/one", 0.5, None), (3, "c/three", 0.1, None)])
    doc = dist.build_digest(cfg, "2026-W43")
    assert [r["repo_id"] for r in doc["new_on_board"]] == [3]
    assert any("Live lists start on 2026-10-19" in n for n in doc["notes"])
    # the feed still lists every repo of the first list as an entry
    assert {e["repo_id"] for e in dist.new_entries(dist.load_board(cfg))} == {1, 2, 3}


def test_placeholder_names_use_the_published_name(env):
    facts = {5: {"name": "real/name"}, 6: {"name": "repo_id=6"}}
    assert dist.display_name(5, "repo_id=5", facts) == "real/name"
    assert dist.display_name(6, "repo_id=6", facts) == "repo_id=6"
    assert dist.display_name(7, "ok/one", facts) == "ok/one"
