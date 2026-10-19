"""Export, schema parity and EDA helpers on tiny tables (no dbt)."""

from __future__ import annotations

import json
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

from breakout import features_dict as fd
from breakout.config import get_config
from breakout.features import build as fb
from breakout.features import eda

LIVE_ONLY = ["repo_id", "snapshot_date", "bucket"]


@pytest.fixture
def tiny(tmp_path, monkeypatch):
    """A warehouse with a two-feature mart + labels, and the build paths redirected into tmp_path."""
    feats = fd.load()
    names = list(feats)[:2]
    wh = tmp_path / "w.duckdb"
    con = duckdb.connect(str(wh))
    con.execute(
        f"create table mart_repo_features (bucket smallint, repo_id bigint, snapshot_date date, {names[0]} integer, {names[1]} double)"
    )
    con.execute(
        "create table mart_labels (repo_id bigint, snapshot_date date, gain_30d integer, threshold_rel double, breakout_rel boolean, breakout_abs boolean, days_to_threshold bigint, first_trending_date date, trending_covered boolean)"
    )
    for i, d in enumerate([date(2020, 1, 6), date(2021, 1, 4)]):
        con.execute("insert into mart_repo_features values (1, ?, ?, ?, ?)", [i + 1, d, i, i / 2])
        con.execute(
            "insert into mart_labels values (?, ?, 3, 100.0, ?, false, null, null, true)",
            [i + 1, d, i == 1],
        )
    # a live-only mart row (no label yet)
    con.execute("insert into mart_repo_features values (1, 9, date '2025-06-02', 5, 1.5)")
    con.close()
    monkeypatch.setattr(fb, "TRAINING_DIR", tmp_path / "training")
    monkeypatch.setattr(fb, "FEATURES_LABELS_DIR", tmp_path / "training" / "features_labels")
    monkeypatch.setattr(fb, "MANIFEST_PATH", tmp_path / "training" / "feature_manifest.json")
    monkeypatch.setattr(fb, "LIVE_DIR", tmp_path / "live")
    return wh, names


def test_export_fails_when_the_mart_has_undocumented_columns(tiny):
    wh, names = tiny
    con = duckdb.connect(str(wh))
    con.execute("alter table mart_repo_features add column surprise integer")
    con.close()
    with pytest.raises(RuntimeError, match="surprise"):
        fb.export_training(get_config(None), wh)


def test_export_training_writes_year_files_manifest_and_matching_live_schema(tiny, monkeypatch):
    wh, names = tiny
    # keep only the two documented columns in the dictionary view used by the exporter
    full = fd.load()
    monkeypatch.setattr(fd, "load", lambda *a, **k: {n: full[n] for n in names})
    man = fb.export_training(get_config(None), wh)
    assert man["rows_per_year"] == {"2020": 1, "2021": 1} and man["rows_total"] == 2
    assert man["features"] == names and man["label_columns"] == fb.LABEL_COLUMNS
    assert json.loads(fb.MANIFEST_PATH.read_text())["dictionary_sha256"] == fd.dictionary_hash()
    f20 = fb.FEATURES_LABELS_DIR / "year=2020" / "part-0.parquet"
    assert f20.exists()
    # the live file of any date has exactly the mart columns, in the same order and types
    live = fb.export_live(date(2025, 6, 2), wh)
    ok, msg = fb.schemas_match(live)
    assert ok, msg
    # a type change in the live file is caught
    con = duckdb.connect()
    bad = live.with_name("bad.parquet")
    con.execute(
        f"copy (select repo_id::integer as repo_id, * exclude (repo_id) from read_parquet('{live}')) to '{bad}' (format parquet)"
    )
    assert not fb.schemas_match(bad)[0]


def test_null_rates_by_year(tiny):
    wh, names = tiny
    con = duckdb.connect(str(wh))
    con.execute(f"update mart_repo_features set {names[0]} = null where repo_id = 2")
    con.close()
    nr = fb.null_rates(wh)
    assert nr[names[0]]["2021"] == 1.0 and nr[names[0]]["2020"] == 0.0
    assert nr[names[0]]["all"] == pytest.approx(1 / 3)


def test_univariate_auc_matches_a_reference_implementation(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    n = 400
    y = rng.random(n) < 0.2
    df = pd.DataFrame(
        {
            "repo_id": np.arange(n),
            "snapshot_date": date(2020, 1, 6),
            "perfect": y.astype(float) + rng.random(n) * 0.1,  # ties-free, separates the classes
            "noise": rng.random(n),
            "ties": rng.integers(0, 3, n).astype(float),
            "mostly_null": np.where(rng.random(n) < 0.7, np.nan, rng.random(n)),
            "breakout_rel": y,
        }
    )
    d = tmp_path / "features_labels" / "year=2020"
    d.mkdir(parents=True)
    df.to_parquet(d / "part-0.parquet")
    monkeypatch.setattr(eda, "FEATURES_LABELS_DIR", tmp_path / "features_labels")
    con = duckdb.connect()
    got = eda.univariate_auc(con, ["perfect", "noise", "ties", "mostly_null"]).set_index("feature")
    from sklearn.metrics import roc_auc_score

    for c in ("perfect", "noise", "ties"):
        assert got.loc[c, "auc"] == pytest.approx(roc_auc_score(df.breakout_rel, df[c]))
    ok = df.dropna(subset=["mostly_null"])
    assert got.loc["mostly_null", "auc"] == pytest.approx(
        roc_auc_score(ok.breakout_rel, ok.mostly_null)
    )
    assert got.loc["mostly_null", "non_null_share"] == pytest.approx(len(ok) / n)
    assert got.index[0] == "perfect"  # sorted by strength


def test_corr_clusters_group_duplicates():
    rng = np.random.default_rng(1)
    a = rng.normal(size=500)
    df = pd.DataFrame(
        {"a": a, "a2": a * 3 + rng.normal(scale=0.01, size=500), "b": rng.normal(size=500)}
    )
    clusters, corr, order = eda.corr_clusters(df, ["a", "a2", "b"])
    assert clusters == [["a", "a2"]] and set(order) == {"a", "a2", "b"}
