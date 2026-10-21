"""End-to-end tests of the site data exporters on a tiny synthetic world (no network)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from breakout import paths as P
from breakout.config import get_config
from breakout.ops import ledger
from breakout.publish import site_data as sd

D = date(2026, 10, 21)


def _pred(
    d: date,
    rows: list[tuple[int, str, float, str | None]],
    suspicion: dict[int, float] | None = None,
) -> pd.DataFrame:
    suspicion = suspicion or {}
    return pd.DataFrame(
        {
            "snapshot_date": d.isoformat(),
            "repo_id": [r[0] for r in rows],
            "repo_name": [r[1] for r in rows],
            "rank": range(1, len(rows) + 1),
            "prob": [r[2] for r in rows],
            "raw_score": [r[2] for r in rows],
            "b1_rank": range(1, len(rows) + 1),
            "explanation": [r[3] for r in rows],
            "top_contribs": [None] * len(rows),
            "model_version": "m1",
            "features_hash": "h",
            "schema_version": 1,
            "suspicion_score": [suspicion.get(r[0]) for r in rows],
        }
    )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path
    out = root / "site" / "public" / "data"
    monkeypatch.setattr(P, "DATA_DIR", root / "data")
    monkeypatch.setattr(P, "ROOT", root)
    monkeypatch.setattr(sd, "SITE_DATA_DIR", out)
    for name, rel in (
        ("LEADERBOARD_JSON", "leaderboard.json"),
        ("STATUS_JSON", "status.json"),
        ("TRACK_RECORD_JSON", "track_record.json"),
        ("BACKTEST_JSON", "backtest.json"),
        ("META_JSON", "meta.json"),
        ("STAR_SNAPSHOTS_JSON", "star_snapshots.json"),
        ("REPOS_DIR", "repos"),
        ("EXPLORER_DIR", "explorer"),
    ):
        monkeypatch.setattr(sd, name, out / rel)
    monkeypatch.setattr(
        sd, "LIVE_PREDICTIONS_PARQUET", out / "explorer" / "live_predictions.parquet"
    )
    monkeypatch.setattr(sd, "OOF_TOP100_PARQUET", out / "explorer" / "oof_top100.parquet")
    monkeypatch.setattr(sd, "CONFIG_HIDDEN_REPOS", root / "hidden.yaml")
    (root / "hidden.yaml").write_text("hidden_repo_ids: [9]\n")
    monkeypatch.setattr(ledger, "LEDGER_PATH", root / "ledger" / "predictions.csv")
    snaps = root / "data" / "snapshots" / "predictions"
    for i, rows in enumerate(
        (
            [(1, "a/one", 0.30, "e1"), (2, "b/two", 0.20, None), (9, "hidden/x", 0.1, None)],
            [(2, "b/two", 0.30, "e2"), (1, "a/one", 0.25, "e1"), (3, "c/three", 0.2, None)],
        )
    ):
        d = D - timedelta(days=2 - i)
        p = snaps / f"date={d}" / "predictions.parquet"
        p.parent.mkdir(parents=True)
        _pred(d, rows).to_parquet(p)
    today = root / "data" / "run" / f"predictions_{D}.parquet"
    today.parent.mkdir(parents=True)
    _pred(
        D,
        [
            (3, "c/three", 0.40, "e3"),
            (1, "a/one", 0.30, "e1"),
            (4, "gone/repo", 0.2, None),
            (9, "hidden/x", 0.1, None),
            (5, "d/five", 0.05, None),
        ],
        suspicion={5: 99.0},
    ).to_parquet(today)
    monkeypatch.setattr(sd.live_stats, "fetch_live_info", lambda cfg, ids: {})
    cfg = get_config(None)
    monkeypatch.setattr(cfg.site, "leaderboard_size", 3, raising=False)
    return cfg, root, today


def test_leaderboard_ranks_history_hidden_and_gone(world):
    cfg, root, today = world
    live = {
        4: {"status": "not_found"},
        3: {
            "status": "ok",
            "name_with_owner": "Real/Three",
            "description": "desc",
            "primary_language": "Rust",
            "stargazer_count_at_fetch": 120,
            "created_at": datetime(2026, 10, 10, tzinfo=UTC),
        },
    }
    con = duckdb.connect()
    _, items = sd.export_leaderboard(cfg, D, today, con, {9}, set(), live)
    assert [i["repo_id"] for i in items] == [3, 1, 5]  # hidden and gone repos are dropped, refilled
    assert [i["rank"] for i in items] == [1, 2, 3]
    by = {i["repo_id"]: i for i in items}
    assert by[3]["repo_name"] == "Real/Three" and by[3]["language"] == "Rust"
    assert by[3]["stars_total_source"] == "github_api" and by[3]["stars_total_observed"] == 120
    assert by[3]["rank_change"] == "up" and by[3]["days_on_board"] == 2  # rank 3 yesterday, 1 today
    assert by[1]["rank_change"] == "same" and by[1]["days_on_board"] == 3  # on the board 3 days
    assert by[1]["first_flagged_date"] == (D - timedelta(days=2)).isoformat()
    assert by[5]["rank_change"] == "new" and by[5]["days_on_board"] == 1
    assert by[5]["suspicion_score"] == 99.0 and by[5]["suspicion_level"] == "high"
    assert json.loads((root / "site/public/data/leaderboard.json").read_text())[0]["repo_id"] == 3


def test_track_record_with_outcomes_and_ledger(world):
    cfg, root, today = world
    old = D - timedelta(days=31)
    pdir = root / "data" / "snapshots" / "predictions" / f"date={old}"
    odir = root / "data" / "snapshots" / "outcomes" / f"date={old}"
    pdir.mkdir(parents=True)
    odir.mkdir(parents=True)
    rows = [(i, f"o/r{i}", 0.3 - i / 100, None) for i in range(1, 31)]
    _pred(old, rows).to_parquet(pdir / "predictions.parquet")
    pd.DataFrame(
        {
            "repo_id": [r[0] for r in rows],
            "label": [1 if r[0] <= 5 else 0 for r in rows],
            "gain_30d": [900.0 if r[0] <= 5 else 4.0 for r in rows],
        }
    ).to_parquet(odir / "outcomes.parquet")
    ledger.append_entry(old, "m1", 30, pdir / "predictions.parquet", "abc")
    p = sd.export_track_record(cfg, duckdb.connect())
    doc = json.loads(p.read_text())
    assert doc["summary"]["n_matured_days"] == 1
    assert doc["matured_snapshots"][0]["precision_at_25"] == pytest.approx(5 / 25)
    assert doc["matured_snapshots"][0]["top25"][0]["hit"] is True
    assert doc["ledger"]["verified"] is True and doc["ledger"]["total_rows"] == 1


def test_track_record_without_data_is_honest(world):
    cfg, root, today = world
    doc = json.loads(sd.export_track_record(cfg, duckdb.connect()).read_text())
    assert doc["summary"]["n_matured_days"] == 0
    assert doc["matured_snapshots"] == []
    assert doc["ledger"]["verified"] is False


def test_status_and_meta(world):
    cfg, root, today = world
    (root / "data" / "run" / "status.json").write_text(
        json.dumps({"steps": [{"step": "2_ingest", "duration_s": 3.14159}], "missing_hours": ["x"]})
    )
    (root / "data" / "models").mkdir(parents=True)
    (root / "data" / "models" / "registry.json").write_text(
        json.dumps(
            {
                "champion": "v1",
                "versions": [
                    {
                        "version": "v1",
                        "registered_at": "2026-10-19",
                        "metrics": {
                            "cv_pooled": {"pr_auc": 0.1},
                            "holdout": {"eval_model": {"pr_auc": 0.15}},
                        },
                    }
                ],
            }
        )
    )
    (root / "reports" / "dbt").mkdir(parents=True)
    (root / "reports" / "dbt" / "summary.json").write_text('{"tests": 274}')
    st = json.loads(sd.export_status(cfg, D, 3).read_text())
    assert st["step_durations"] == {"2_ingest": 3.14}
    assert st["model"]["version"] == "v1" and st["model"]["holdout_pr_auc"] == 0.15
    assert st["dbt_summary"] == {"tests_passing": 274, "status": "clean"}
    assert st["missing_hours"] == ["x"]
    meta = json.loads(sd.export_meta(cfg, D, 3, 4, 0, 5).read_text())
    assert meta["model_version"] == "v1" and meta["counts"]["detail_pages"] == 4


def test_dbt_summary_unknown_without_file(world):
    assert sd.dbt_summary() == {"tests_passing": None, "status": "unknown"}


def test_ingest_summary_counts_the_previous_day(tmp_path: Path):
    d = tmp_path / "events" / "event_type=WatchEvent" / "year=2026" / "month=10"
    d.mkdir(parents=True)
    ts = pd.to_datetime(
        ["2026-10-20 05:00", "2026-10-20 23:59", "2026-10-21 00:30", "2026-10-19 12:00"]
    )
    pd.DataFrame({"created_at": ts, "repo_id": [1, 2, 3, 4]}).to_parquet(d / "month-202610.parquet")
    (tmp_path / "events" / "event_type=ForkEvent").mkdir(parents=True)  # no files: skipped
    got = sd.ingest_summary(D, lake=tmp_path)
    assert got == [
        {"event_type": "WatchEvent", "latest_event": "2026-10-20T23:59:00", "rows_24h": 2}
    ]
    assert sd.ingest_summary(D, lake=tmp_path / "missing") == []


def test_restore_star_snapshots_noop_when_present(world, monkeypatch):
    cfg, root, _ = world
    sd.STAR_SNAPSHOTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    sd.STAR_SNAPSHOTS_JSON.write_text("{}")
    sd._restore_star_snapshots(cfg)  # would raise on the network if it tried
    assert sd.STAR_SNAPSHOTS_JSON.read_text() == "{}"


def _enrich(root: Path) -> None:
    e = root / "data" / "derived" / "enrich"
    e.mkdir(parents=True)
    pd.DataFrame(
        {
            "repo_id": [3],
            "name_with_owner": ["Real/Three"],
            "description": ["A repo"],
            "primary_language": ["Rust"],
            "created_at": [pd.Timestamp("2026-10-10")],
            "owner_type": ["User"],
            "is_fork": [False],
            "parent_repo_id": [None],
            "is_archived": [False],
            "is_mirror": [False],
            "is_template": [False],
            "license_spdx": ["MIT"],
            "topics": [["x", "y"]],
            "homepage_url": [None],
            "fetched_at": [pd.Timestamp("2026-10-20")],
            "owner_id": [77],
            "owner_login": ["Real"],
        }
    ).to_parquet(e / "repo_metadata.parquet")
    pd.DataFrame(
        {
            "repo_id": [3],
            "date": [date(2026, 10, 19)],
            "rank": [4],
            "language_filter": [None],
            "source": ["s"],
        }
    ).to_parquet(e / "trending.parquet")
    pd.DataFrame(
        {
            "repo_id": [3],
            "title": ["Show HN"],
            "url": ["https://x"],
            "story_id": [42],
            "created_at": [pd.Timestamp("2026-10-18")],
            "points": [120],
            "num_comments": [30],
        }
    ).to_parquet(e / "hn_stories.parquet")


def test_repo_details_collect_history_enrichment_and_outcomes(world):
    cfg, root, today = world
    _enrich(root)
    odir = root / "data" / "snapshots" / "outcomes" / f"date={D - timedelta(days=1)}"
    odir.mkdir(parents=True)
    pd.DataFrame(
        {"repo_id": [3], "label": [1], "gain_30d": [600.0], "snapshot_date": ["2026-10-20"]}
    ).to_parquet(odir / "outcomes.parquet")
    con = duckdb.connect()
    live = {3: {"status": "ok", "stargazer_count_at_fetch": 500, "name_with_owner": "Real/Three"}}
    _, items = sd.export_leaderboard(cfg, D, today, con, set(), set(), live)
    written = sd.export_repo_details(cfg, D, items, con, live)
    docs = {int(p.stem): json.loads(p.read_text()) for p in written}
    assert set(docs) >= {1, 3}
    d3 = docs[3]
    assert d3["repo_name"] == "Real/Three"
    assert d3["metadata"]["license_spdx"] == "MIT" and d3["metadata"]["topics"] == ["x", "y"]
    assert d3["trending_appearances"][0]["rank"] == 4
    assert d3["hn_stories"][0]["hn_url"].endswith("id=42") and d3["hn_stories"][0]["points"] == 120
    assert d3["stars_total"] == 500 and d3["stars_total_source"] == "github_api"
    assert [p["date"] for p in d3["prediction_history"]] == sorted(
        p["date"] for p in d3["prediction_history"]
    )
    assert d3["realized_outcome"]["matured"] is True and d3["realized_outcome"]["hit"] is True
    # a stale page of a repo no longer flagged is removed
    (sd.REPOS_DIR / "123.json").write_text("{}")
    sd.export_repo_details(cfg, D, items, con, live)
    assert not (sd.REPOS_DIR / "123.json").exists()


def test_metadata_and_suspicion_helpers_without_warehouse(world):
    cfg, root, today = world
    _enrich(root)
    con = duckdb.connect()
    m = sd._get_repo_metadata_map([3, 99], con)
    assert set(m) == {3} and m[3]["owner_login"] == "Real"
    assert sd._get_repo_metadata_map([], con) == {}
    df = _pred(D, [(5, "d/five", 0.1, None)], suspicion={5: 91.0})
    s = sd._get_suspicion_map([5, 6], D, con, df)
    assert s[5]["score"] == 91.0 and s[5]["level"] == "medium"
    assert s[6]["score"] is None and s[6]["level"] == "low" and s[6]["reasons"] == []
    spark = sd._get_spark_stars([1, 2], D, con)
    assert spark[1] == [0] * 28


def test_publish_site_data_end_to_end(world, monkeypatch):
    cfg, root, today = world
    monkeypatch.setattr(sd, "_restore_star_snapshots", lambda cfg: None)
    monkeypatch.setattr(sd.distribution_mod, "restore_snapshots", lambda cfg, today=None: 0)
    monkeypatch.setattr(sd.distribution_mod, "pull_digests", lambda cfg: 0)
    monkeypatch.setattr(
        sd.distribution_mod, "SNAP_PRED", root / "data" / "snapshots" / "predictions"
    )
    monkeypatch.setattr(sd.distribution_mod, "SNAP_OUT", root / "data" / "snapshots" / "outcomes")
    monkeypatch.setattr(sd.distribution_mod, "DATA_DIR", sd.SITE_DATA_DIR)
    monkeypatch.setattr(sd.distribution_mod, "BADGES_DIR", root / "site" / "public" / "badges")
    monkeypatch.setattr(
        sd.distribution_mod, "FEED_ITEMS_JSON", sd.SITE_DATA_DIR / "feed_items.json"
    )
    monkeypatch.setattr(sd.distribution_mod, "_hidden", lambda: (set(), set()))
    monkeypatch.setattr(sd.insights_mod, "export_insights_data", lambda con=None: None)
    lb, st = sd.publish_site_data(cfg, D, today, upload=False)
    out = sd.SITE_DATA_DIR
    for f in ("leaderboard.json", "status.json", "track_record.json", "backtest.json", "meta.json"):
        assert (out / f).exists(), f
    assert (out / "feed_items.json").exists()
    assert (root / "site" / "public" / "badges").exists()
    assert (out / "explorer" / "live_predictions.parquet").exists()
    assert json.loads((out / "meta.json").read_text())["data_through"] == D.isoformat()
