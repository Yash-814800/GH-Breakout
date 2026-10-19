import math
from datetime import date

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score

from breakout.ml import metrics as M

D1, D2, D3 = date(2024, 1, 1), date(2024, 1, 8), date(2025, 1, 6)


def frame():
    # D1: ranking by score = repo 1,2,3,4; positives are 1 and 3
    # D2: positives {5}; ranking 6,5 -> AP 0.5
    # D3: no positive
    rows = [
        (1, D1, 0.9, True), (2, D1, 0.8, False), (3, D1, 0.7, True), (4, D1, 0.1, False),
        (5, D2, 0.4, True), (6, D2, 0.6, False),
        (7, D3, 0.5, False), (8, D3, 0.2, False),
    ]  # fmt: skip
    return pd.DataFrame(rows, columns=["repo_id", "snapshot_date", "score", "label"])


def test_per_snapshot_hand_computed():
    s = M.per_snapshot(frame(), [1, 2])
    assert s.loc[D1, "precision@1"] == 1.0
    assert s.loc[D1, "precision@2"] == 0.5
    assert s.loc[D1, "recall@2"] == 0.5
    assert s.loc[D1, "ap"] == pytest.approx((1 + 2 / 3) / 2)
    assert s.loc[D2, "precision@1"] == 0.0
    assert s.loc[D2, "ap"] == pytest.approx(0.5)
    assert s.loc[D2, "recall@2"] == 1.0
    assert s.loc[D3, "precision@2"] == 0.0
    assert math.isnan(s.loc[D3, "ap"]) and math.isnan(s.loc[D3, "recall@1"])


def test_precision_at_k_larger_than_candidates_divides_by_k():
    s = M.per_snapshot(frame(), [10])
    assert s.loc[D1, "precision@10"] == pytest.approx(0.2)


def test_ties_broken_by_repo_id():
    df = pd.DataFrame(
        {"repo_id": [2, 1], "snapshot_date": [D1, D1], "score": [1.0, 1.0], "label": [False, True]}
    )
    assert M.per_snapshot(df, [1]).loc[D1, "precision@1"] == 1.0  # repo 1 ranks first


def test_pooled_matches_sklearn():
    df = frame()
    p = M.pooled(df)
    assert p["pr_auc"] == pytest.approx(average_precision_score(df["label"], df["score"]))
    assert p["positive_rate"] == pytest.approx(3 / 8)
    assert p["n_pos"] == 3
    # 3 positives with scores .9 .7 .4; negatives .8 .6 .5 .2 .1 -> pairs ordered correctly: 5+4...
    assert p["roc_auc"] == pytest.approx(11 / 15)


def test_calibration_metrics():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.9, 0.1, 0.6, 0.4])
    assert M.brier(y, p) == pytest.approx((0.01 + 0.01 + 0.16 + 0.16) / 4)
    assert M.log_loss(y, p) == pytest.approx(
        -(math.log(0.9) + math.log(0.9) + math.log(0.6) + math.log(0.6)) / 4
    )
    # one bin per row -> ECE = mean |y - p|
    assert M.ece(y, p, n_bins=4) == pytest.approx((0.1 + 0.1 + 0.4 + 0.4) / 4)
    # a perfectly calibrated single bin
    assert M.ece(np.array([1, 0]), np.array([0.5, 0.5]), n_bins=1) == pytest.approx(0.0)
    assert "ece" in M.pooled(frame().assign(prob=0.5))


def test_by_year_groups_snapshots():
    s = M.per_snapshot(frame(), [1])
    y = M.by_year(s)
    assert list(y.index) == [2024, 2025]
    assert y.loc[2024, "n_snapshots"] == 2
    assert y.loc[2024, "precision@1"] == pytest.approx(0.5)


def test_block_indices_shape_and_range():
    rng = np.random.default_rng(0)
    idx = M.block_indices(10, 4, rng)
    assert len(idx) == 10 and idx.min() >= 0 and idx.max() < 10
    assert M.block_indices(3, 10, rng).max() < 3


def test_bootstrap_ci_brackets_mean_and_is_deterministic():
    s = M.per_snapshot(frame(), [1])
    a = M.bootstrap_ci(s, columns=["precision@1"], n_boot=200, block=1)
    b = M.bootstrap_ci(s, columns=["precision@1"], n_boot=200, block=1)
    assert a.equals(b)
    r = a.loc["precision@1"]
    assert r.ci_low <= r["mean"] <= r.ci_high


def test_weighted_ap_equals_sklearn_with_ties():
    rng = np.random.default_rng(1)
    s = rng.integers(0, 5, 200).astype(float)
    y = (rng.random(200) < 0.2).astype(float)
    order = np.argsort(-s, kind="stable")
    ss, yy = s[order], y[order]
    tie_end = np.concatenate([ss[1:] != ss[:-1], [True]])
    assert M._weighted_ap(yy, np.ones(200), tie_end) == pytest.approx(average_precision_score(y, s))


def test_pooled_bootstrap_point_estimate():
    df = frame()
    r = M.bootstrap_pooled_pr_auc(df, n_boot=50, block=1)
    assert r["pr_auc"] == pytest.approx(average_precision_score(df["label"], df["score"]))
    assert r["ci_low"] <= r["ci_high"]


def test_lead_time_report():
    d0, d1, d2 = date(2024, 1, 1), date(2024, 1, 8), date(2024, 1, 15)
    preds = pd.DataFrame(
        {
            "repo_id": [1, 2, 1, 2, 3, 1, 2],
            "snapshot_date": [d0, d0, d1, d1, d1, d2, d2],
            "score": [9, 1, 9, 5, 7, 9, 5],
        }
    )
    t = lambda s: pd.Timestamp(s)  # noqa: E731
    labels = pd.DataFrame(
        {
            "repo_id": [1, 1, 2, 3, 3, 4],
            "snapshot_date": [d0, d1, d0, d1, d1, d0],
            "first_trending_date": [t("2024-01-15"), t("2024-01-15"), pd.NaT, t("2024-01-12"),
                                    t("2024-01-12"), t("2024-01-20")],
            "trending_covered": [True, True, True, True, True, False],
        }
    )  # fmt: skip
    r = M.lead_time_report(preds, labels, k=1)
    # repo 1 is top-1 on d0 (lead 14 days); repo 3 is never top-1 -> never flagged
    assert r["n_trending_repos"] == 2  # repo 4 is not covered, repo 2 never trends
    assert r["n_flagged"] == 1
    assert r["median_lead_days"] == 14
    assert r["share_never_flagged"] == pytest.approx(0.5)
    assert r["share_flagged_before_trending"] == pytest.approx(0.5)
