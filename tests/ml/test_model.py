"""Phase 8: dataset, search helpers, calibration, explanations, registry (synthetic data)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from breakout import features_dict
from breakout.config import get_config
from breakout.ml import calibrate as C
from breakout.ml import cv
from breakout.ml import dataset as D
from breakout.ml import explain as E
from breakout.ml import metrics as M
from breakout.ml import registry as G
from breakout.ml import train as T

CFG = get_config()


def mondays(n: int, start: date = date(2018, 1, 1)) -> list[date]:
    return [start + timedelta(days=7 * i) for i in range(n)]


def test_inner_split_has_embargo_and_is_time_ordered():
    dates = mondays(120)
    fit, val = T.inner_split(dates, 3, 30)
    assert max(fit) < min(val)
    assert (min(val) - max(fit)).days >= 30
    assert max(val) == dates[-1]
    assert all(d >= min(val) for d in val)


def test_inner_split_too_short():
    with pytest.raises(ValueError):
        T.inner_split(mondays(4), 3, 30)


def test_sample_rows_keeps_every_positive_and_is_seeded():
    y = np.zeros(10_000, dtype=bool)
    y[::50] = True
    a = T.sample_rows(y, 0.1, 1)
    assert a[y].all()
    assert 0.07 < (a & ~y).sum() / (~y).sum() < 0.13
    assert (a == T.sample_rows(y, 0.1, 1)).all()
    assert T.sample_rows(y, 1.0, 1).all()


def test_config_grid_is_seeded_distinct_and_within_the_grid():
    a = T.config_grid(CFG, 12, 42)
    assert a == T.config_grid(CFG, 12, 42)
    assert len({json.dumps(c, sort_keys=True) for c in a}) == 12
    for c in a:
        assert c["num_leaves"] in CFG.model.grid["num_leaves"]
        assert c["scale_pos_weight"] in CFG.model.scale_pos_weight


def test_feature_list_never_contains_keys_or_labels():
    feats = D.feature_columns()
    assert not set(feats) & D.FORBIDDEN
    with pytest.raises(AssertionError):
        D.assert_feature_list(["stars_7d", "breakout_rel"])
    with pytest.raises(AssertionError):
        D.assert_feature_list(["repo_id"])


def test_live_features_are_the_dictionary_live_subset():
    d = features_dict.load()
    assert set(D.feature_columns()) == {
        f for f, e in d.items() if e["allowed"] and e["live_available"]
    }


def test_categories_fixed_from_fold_and_unseen_become_other():
    train = pd.DataFrame(
        {"primary_language": ["Python", "Go", "Other"], "owner_type": ["User"] * 3}
    )
    cats = D.fit_categories(train)
    assert cats["primary_language"] == ["Go", "Python", "Other"]
    test = pd.DataFrame(
        {"primary_language": ["Rust", "Go", None], "owner_type": ["Bot", "User", "User"]}
    )
    out = D.apply_categories(test, cats)
    assert list(out["primary_language"]) == ["Other", "Go", "Other"]
    assert list(out["owner_type"].cat.categories) == ["User", "Other"]
    assert list(out["owner_type"]) == ["Other", "User", "User"]


def test_isotonic_calibrator_roundtrip_and_monotone():
    rng = np.random.default_rng(0)
    s = rng.random(5000)
    y = rng.random(5000) < s**3
    cal = C.fit_calibrator(s, y, min_positives=50)
    assert cal.kind == "isotonic"
    back = C.Calibrator.from_json(json.dumps(cal.to_json()))
    grid = np.linspace(0, 1, 50)
    p = back.predict(grid)
    assert (np.diff(p) >= -1e-12).all()
    assert np.allclose(p, cal.predict(grid))
    assert abs(back.predict(np.array([0.9]))[0] - 0.9**3) < 0.12


def test_platt_fallback_below_min_positives_and_identity_without_positives():
    rng = np.random.default_rng(1)
    s = rng.random(2000) * 0.1
    y = rng.random(2000) < s
    cal = C.fit_calibrator(s, y, min_positives=10_000)
    assert cal.kind == "platt"
    assert np.all((cal.predict(s) > 0) & (cal.predict(s) < 1))
    assert C.fit_calibrator(s, np.zeros(2000, bool)).kind == "identity"


def test_reliability_table_counts():
    y = np.array([0, 0, 1, 1] * 25)
    p = np.linspace(0, 1, 100)
    t = C.reliability_table(y, p, 10)
    assert t["n"].sum() == 100 and t["n_pos"].sum() == 50 and len(t) == 10


def test_permutation_keeps_snapshot_label_counts():
    y = np.array([1, 0, 0, 0, 1, 1, 0, 0], dtype=bool)
    snaps = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    out = cv._permute_within_snapshot(y, snaps, 3)
    for s in (1, 2):
        assert out[snaps == s].sum() == y[snaps == s].sum()


# ---- explanations ----------------------------------------------------------------------------

FEATS = features_dict.load()


def test_format_value_units():
    f = lambda n, v: E.format_value(n, v, FEATS[n])  # noqa: E731
    assert f("sg_share_experienced", 0.724)[0] == "72%"
    assert f("median_first_response_hours_28d", 3.2)[0] == "~3"
    assert f("median_first_response_hours_28d", 0.2)[0] == "<1"
    assert f("stars_7d", 1234.0)[0] == "1,234"
    assert f("star_ratio_7d", 2.46)[0] == "2.5"
    assert f("primary_language", "Rust")[0] == "Rust"


def test_phrase_chooses_high_or_low_by_reference_and_skips_missing():
    ref = {"stars_7d": 20.0}
    assert E.phrase("stars_7d", 80.0, ref, FEATS) == "80 stars in the last week"
    assert E.phrase("stars_7d", 3.0, ref, FEATS) == "few stars in the last week"
    assert E.phrase("stars_7d", float("nan"), ref, FEATS) is None
    assert E.phrase("primary_language", "Unknown", {}, FEATS) == "language unknown"


def test_explain_sentence_example_from_the_phase_file():
    row = {
        "sg_share_experienced": 0.72,
        "median_first_response_hours_28d": 3.0,
        "new_contributors_28d": 3.0,
        "star_max_hour_share_7d": 0.9,
        "age_days": 4.0,
    }
    ref = {
        "sg_share_experienced": 0.3,
        "median_first_response_hours_28d": 20.0,
        "new_contributors_28d": 0.0,
        "star_max_hour_share_7d": 0.3,
        "age_days": 30.0,
    }
    contribs = [
        ("sg_share_experienced", 0.9),
        ("median_first_response_hours_28d", 0.4),
        ("new_contributors_28d", 0.3),
        ("star_max_hour_share_7d", -0.5),
    ]
    s = E.explain_sentence(row, contribs, ref, FEATS)
    assert s == (
        "Flagged because 72% of recent stars come from experienced accounts, "
        "issues get a first reply within ~3 hours and 3 new contributors in four weeks. "
        "Held back by: 90% of the last week's stars came in one hour."
    )


def test_inverted_features_pick_the_phrase_by_the_small_value():
    ref = {"age_days": 30.0, "median_first_response_hours_28d": 20.0}
    assert E.phrase("age_days", 4.0, ref, FEATS) == "only 4 days old"
    assert E.phrase("age_days", 90.0, ref, FEATS) == "90 days old"
    assert "within ~3 hours" in E.phrase("median_first_response_hours_28d", 3.0, ref, FEATS)
    assert "wait long" in E.phrase("median_first_response_hours_28d", 70.0, ref, FEATS)


def test_explain_sentence_without_contributions():
    assert E.explain_sentence({}, [], {}, FEATS) == "No single feature stands out."


def test_top_contributions_order_and_counts():
    sv = np.array([0.5, -0.2, 0.9, 0.1, -0.7, 0.3])
    names = list("abcdef")
    top = E.top_contributions(sv, names)
    assert [n for n, _ in top] == ["c", "a", "f", "e", "b"]
    assert [n for n, _ in E.top_contributions(sv, names, skip={"c"})][:2] == ["a", "f"]


def tiny_model():
    import lightgbm as lgb

    rng = np.random.default_rng(0)
    X = pd.DataFrame(
        {
            "stars_7d": rng.integers(0, 100, 3000).astype(np.float32),
            "sg_share_experienced": rng.random(3000).astype(np.float32),
            "primary_language": rng.choice(["Python", "Go", "Unknown"], 3000),
        }
    )
    y = (X["stars_7d"] / 100 + X["sg_share_experienced"] + rng.normal(0, 0.3, 3000)) > 1.5
    cats = D.fit_categories(X)
    Xc = D.apply_categories(X, cats)
    b = lgb.train(
        {"objective": "binary", "verbose": -1, "num_threads": 1, "seed": 1, "deterministic": True},
        lgb.Dataset(Xc, y.astype(int), categorical_feature=["primary_language"]),
        30,
    )
    return b, X, cats


def test_shap_contributions_sum_to_the_raw_margin():
    b, X, cats = tiny_model()
    Xc = D.apply_categories(X.head(50), cats)
    sv = E.shap_values(b, Xc)
    assert sv.shape == (50, 3)
    margin = b.predict(Xc, raw_score=True)
    # TreeSHAP: sum of contributions + expected value = margin
    import shap

    base = float(np.ravel(shap.TreeExplainer(b).expected_value)[-1])
    assert np.allclose(sv.sum(axis=1) + base, margin, atol=1e-4)


def test_package_roundtrip_and_predict(tmp_path):
    b, X, cats = tiny_model()
    ref = E.reference_medians(X)
    cal = C.Calibrator("identity")
    G.save_package(tmp_path / "v1", b, cal, cats, list(X.columns), ref, {"m": 1}, "card")
    for f in G.PACKAGE_FILES:
        assert (tmp_path / "v1" / f).exists()
    m = G.load_model(tmp_path / "v1")
    out = G.predict(m, X.head(5))
    raw = b.predict(D.apply_categories(X.head(5), cats))
    assert np.allclose(out["raw_score"], raw)
    assert list(out.columns)[:2] == ["raw_score", "prob"]
    assert len(out["top_contribs"].iloc[0]) <= 5
    assert isinstance(out["explanation"].iloc[0], str)


def test_registry_register_and_champion(tmp_path):
    reg = G.empty_registry()
    reg = G.register(reg, "v1", {"a": 1}, {"promote": False})
    assert reg["champion"] is None
    reg = G.register(reg, "v2", {"a": 2}, {"promote": True})
    assert reg["champion"] == "v2"
    reg = G.register(reg, "v2", {"a": 3}, {"promote": True})
    assert [v["version"] for v in reg["versions"]] == ["v1", "v2"]
    G.save_registry(reg, tmp_path / "registry.json")
    assert G.load_registry(tmp_path / "registry.json")["champion"] == "v2"
    assert G.load_registry(tmp_path / "none.json")["champion"] is None
    with pytest.raises(LookupError):
        G.load_champion(root=tmp_path / "empty")


def scored(n_snap=40, per=60, seed=0, signal=1.0):
    rng = np.random.default_rng(seed)
    rows = []
    for s, d in enumerate(mondays(n_snap)):
        for r in range(per):
            lab = rng.random() < 0.05
            rows.append((s * per + r, d, rng.normal() + signal * lab, lab))
    return pd.DataFrame(rows, columns=["repo_id", "snapshot_date", "score", "label"])


def test_decide_promotes_only_a_clearly_better_candidate():
    good = scored(signal=2.0)
    base = good.assign(score=np.random.default_rng(5).normal(size=len(good)))
    d = G.decide(good, base, None, [10, 25], 200, 25)
    assert d["promote"] and d["vs_B1"]["beats"]
    # a candidate no better than the baseline is not promoted
    d2 = G.decide(base, good, None, [10, 25], 200, 25)
    assert not d2["promote"]
    # must also beat the champion
    d3 = G.decide(good, base, good.assign(score=good["score"] + 0.0), [10, 25], 200, 25)
    assert not d3["promote"]


def test_paired_pr_auc_difference_detects_a_better_ranker():
    a = scored(signal=2.5, seed=1)
    b = a.assign(score=np.random.default_rng(2).normal(size=len(a)))
    r = M.bootstrap_pooled_pr_auc_diff(a, b, n_boot=200)
    assert r["diff"] > 0 and r["ci_low"] > 0 and r["p_not_better"] < 0.05
    same = M.bootstrap_pooled_pr_auc_diff(a, a, n_boot=50)
    assert same["diff"] == 0 and same["ci_low"] == 0 == same["ci_high"]
    ps = M.paired_snapshot_diff(
        M.per_snapshot(a, [25]), M.per_snapshot(b, [25]), ["precision@25"], n_boot=100
    )
    assert ps.loc["precision@25", "mean"] > 0


def test_fit_calibrated_end_to_end_on_a_synthetic_world():
    rng = np.random.default_rng(3)
    dates = mondays(110)
    per = 120
    n = per * len(dates)
    snap = np.repeat(np.array(dates, dtype="datetime64[ns]"), per)
    x1 = rng.normal(size=n)
    y = rng.random(n) < 1 / (1 + np.exp(-(2 * x1 - 4)))
    X = pd.DataFrame(
        {"stars_7d": x1.astype(np.float32), "noise": rng.normal(size=n).astype(np.float32)}
    )
    cfg = CFG.model_copy(
        update={"model": CFG.model.model_copy(update={"max_rounds": 60, "negative_sample": 0.5})}
    )
    fm = T.fit_calibrated(cfg, X, y, snap, dates, n_configs=2)
    assert fm.stats["fit_dates"][1] < fm.stats["val_dates"][0]
    p = T.predict(fm.booster, X, fm.categories)
    # the informative feature is picked up (never evaluated on the fitting rows' in-sample AP claim)
    from sklearn.metrics import roc_auc_score

    assert roc_auc_score(y, p) > 0.75
    imp = dict(zip(X.columns, fm.booster.feature_importance("gain"), strict=True))
    assert imp["stars_7d"] > imp["noise"]
    assert 0 < fm.calibrator.predict(p).mean() < 1


def test_daily_check_evaluate_by_weekday(tmp_path, monkeypatch):
    from breakout.ml import daily_check as DC

    b, X, cats = tiny_model()
    root = tmp_path / "models"
    ref = E.reference_medians(X)
    G.save_core(root / "v1" / "eval_model", b, C.Calibrator("identity"), cats, list(X.columns), ref)
    monkeypatch.setattr(G, "models_dir", lambda: root)
    rng = np.random.default_rng(0)
    days = [date(2025, 3, 24) + timedelta(days=i) for i in range(28)]
    n = 400
    frames = []
    for d in days:
        s7 = rng.integers(0, 100, n).astype(float)
        f = pd.DataFrame(
            {
                "repo_id": np.arange(n),
                "snapshot_date": pd.Timestamp(d),
                "stars_7d": s7,
                "stars_1d": np.minimum(s7, 3.0),
                "stars_total_before": 50.0,
                "star_accel_7d": rng.integers(-5, 5, n).astype(float),
                "sg_share_experienced": rng.random(n),
                "primary_language": rng.choice(["Python", "Go", "Unknown"], n),
            }
        )
        f["breakout_rel"] = (f["stars_7d"] / 100 + f["sg_share_experienced"]) > 1.55
        frames.append(f)
    path = tmp_path / "range.parquet"
    pd.concat(frames).to_parquet(path)
    res = DC.evaluate(CFG, "v1", path)
    assert res["n_snapshots"] == 28
    assert [r["weekday"] for r in res["by_weekday"]] == DC.WEEKDAYS
    assert all(r["snapshots"] == 4 for r in res["by_weekday"])
    assert res["observed_over_expected"]["monday"] > 0
    assert "Mondays minus other days" in res["markdown"]


def test_load_training_reads_years_casts_and_keeps_order(tmp_path):
    for yr, n in ((2020, 5), (2021, 4)):
        d = tmp_path / f"year={yr}"
        d.mkdir()
        pd.DataFrame(
            {
                "bucket": 1,
                "repo_id": np.arange(n)[::-1] + yr * 10,
                "snapshot_date": pd.to_datetime([f"{yr}-01-04"] * n),
                "stars_7d": np.arange(n, dtype="int32"),
                "primary_language": ["Go", "Rust", "Go", None, "Go"][:n],
                "gain_30d": 3,
                "threshold_rel": 100.0,
                "breakout_rel": [True, False, False, False, False][:n],
                "breakout_abs": False,
                "days_to_threshold": pd.array([None] * n, dtype="Int64"),
                "first_trending_date": pd.to_datetime([None] * n),
                "trending_covered": False,
            }
        ).to_parquet(d / "part-0.parquet")
    X, y, meta = D.load_training(features=["stars_7d", "primary_language"], path=tmp_path)
    assert len(X) == 9 and X["stars_7d"].dtype == np.float32
    assert y.dtype == bool and y.sum() == 2
    assert list(meta["repo_id"][:5]) == sorted(meta["repo_id"][:5])
    assert set(meta.columns) >= {"repo_id", "snapshot_date", "gain_30d", "first_trending_date"}
    X20, _, _ = D.load_training(years=[2021], features=["stars_7d"], path=tmp_path)
    assert len(X20) == 4
    with pytest.raises(AssertionError):
        D.load_training(features=["gain_30d"], path=tmp_path)


def test_coverage_bucket_and_slice_table():
    from breakout.ml import cv_report as R

    v = pd.Series([np.nan, 0.0, 0.5, 1.0])
    assert list(R.coverage_bucket(v)) == [
        "NULL (spine only)",
        "none (0)",
        "partial (0, 1)",
        "full (1)",
    ]
    a = scored(signal=2.0)
    b = a.assign(score=np.random.default_rng(1).normal(size=len(a)))
    key = pd.Series(np.where(a["repo_id"] % 2 == 0, "even", "odd"), index=a.index)
    t = R.slice_table(a, b, key, "grp", min_pos=5)
    assert set(t["grp"]) == {"even", "odd"}
    assert (t["model PR-AUC"] > t["B1 PR-AUC"]).all()
