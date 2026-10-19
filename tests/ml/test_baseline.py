from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from breakout.ml import baseline as B
from breakout.ml.splits import make_folds


def toy(n_weeks=160, per=30, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    start = date(2016, 1, 4)
    rid = 0
    for w in range(n_weeks):
        d = start + timedelta(days=7 * w)
        for _ in range(per):
            rid += 1
            s7 = int(rng.integers(0, 40))
            rows.append(
                {
                    "repo_id": rid,
                    "snapshot_date": d,
                    "stars_7d": s7,
                    "stars_1d": min(s7, int(rng.integers(0, 10))),
                    "stars_prev_7d": int(rng.integers(0, 40)),
                    "stars_total_before": int(rng.integers(5, 190)),
                    "label": bool(rng.random() < 0.01 + 0.002 * s7),
                }
            )
    return pd.DataFrame(rows)


def test_scores_follow_definitions():
    df = pd.DataFrame(
        {
            "stars_7d": [10, 10],
            "stars_1d": [2, 5],
            "stars_prev_7d": [4, 4],
            "stars_total_before": [20, 90],
        }
    )
    b1 = B.BASELINES["B1"](df)
    assert (
        b1[1] > b1[0] > 10
    )  # tie on stars_7d broken by stars_1d, never overtakes a higher stars_7d
    assert B.BASELINES["B2"](df).tolist() == pytest.approx([10 / 30, 10 / 100])
    assert B.BASELINES["B3"](df).tolist() == [6, 6]


def test_run_baselines_uses_only_test_rows_and_prob_in_unit_interval():
    df = toy()
    dates = sorted(df["snapshot_date"].unique())
    folds = make_folds(
        dates, test_window_months=3, embargo_days=30, min_train_years=2, horizon_days=30
    )
    preds = B.run_baselines(df, folds)
    assert set(preds) == {"B1", "B2", "B3"}
    test_dates = {d for f in folds for d in f.test_dates}
    assert set(preds["B1"]["snapshot_date"]) == test_dates
    assert preds["B1"]["prob"].between(0, 1).all()
    assert "prob" not in preds["B2"].columns
    # B1 informative in this toy set: higher score, higher probability
    for _, g in preds["B1"].groupby("fold"):  # one isotonic fit per fold
        assert g.sort_values("score")["prob"].is_monotonic_increasing


def test_isotonic_fit_on_train_only():
    df = toy()
    train = df.iloc[:300]
    iso = B.fit_isotonic(train, B.BASELINES["B1"](train))
    assert 0 <= iso.predict([0.0, 1000.0]).min() <= iso.predict([0.0, 1000.0]).max() <= 1


def test_sanity_tables_and_dates():
    df = toy().assign(gain_30d=1, repo_name_at_D="a/b")
    dates = sorted(df["snapshot_date"].unique())
    pick = B.pick_sanity_dates(dates)
    assert len(pick) == 3 and pick == sorted(pick)
    t = B.sanity_tables(df, pick)
    assert all(len(v) == 10 for v in t.values())
    first = next(iter(t.values()))
    assert first["stars_7d"].is_monotonic_decreasing
