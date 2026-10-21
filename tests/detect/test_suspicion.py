"""Unit tests for suspicious growth scoring, cosine similarity, and cohorts (Phase 11)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from breakout.detect import cohorts, scoring, similarity


def test_robust_zscore_basic() -> None:
    # Standard values with known median and MAD
    # Data: [10, 10, 10, 10, 20] -> median = 10, dev = [0, 0, 0, 0, 10] -> MAD = 0
    # Fallback to mean absolute deviation
    z = scoring.robust_zscore(x=20.0, med=10.0, mad=0.0, fallback_mad=2.5)
    assert z > 0
    assert z <= 6.0

    # Normal distribution scale factor test
    # If MAD = 1.0, scale = 1.4826
    z_norm = scoring.robust_zscore(x=11.4826, med=10.0, mad=1.0)
    assert pytest.approx(z_norm, abs=1e-3) == 1.0

    # Clipping to [0, 6]
    z_neg = scoring.robust_zscore(x=5.0, med=10.0, mad=1.0)
    assert z_neg == 0.0  # clipped to min 0.0

    z_huge = scoring.robust_zscore(x=100.0, med=10.0, mad=1.0)
    assert z_huge == 6.0  # clipped to max 6.0


def test_compute_signals_zscores_and_weights() -> None:
    df = pd.DataFrame(
        {
            "repo_id": [1, 2, 3, 4, 5],
            "snapshot_date": ["2024-01-01"] * 5,
            "s_new_accounts": [0.0, 0.1, 0.1, 0.2, 0.9],
            "s_inactive": [0.0, 0.0, 0.1, 0.2, 0.8],
            "s_bulk": [0.0, 0.0, 0.0, 0.0, 0.5],
            "s_burst": [0.1, 0.2, 0.2, 0.3, 0.95],
            "s_lockstep": [0.0, 0.0, 0.0, 0.0, 0.3],
            "s_no_engagement": [0.2, 0.3, 0.3, 0.4, 1.0],
        }
    )

    z_df = scoring.compute_signals_zscores(df)
    assert "z_s_new_accounts" in z_df.columns
    assert "z_s_burst" in z_df.columns

    # High outlier in row 4 should have highest z-scores
    assert z_df.loc[4, "z_s_new_accounts"] > z_df.loc[0, "z_s_new_accounts"]

    raw = scoring.compute_weighted_raw_score(z_df)
    assert len(raw) == 5
    assert raw[4] == max(raw)
    assert raw[0] == min(raw)


def test_map_empirical_cdf() -> None:
    # In-sample mapping
    scores = np.array([0.5, 1.0, 2.0, 3.0, 5.0])
    cdf = scoring.map_empirical_cdf(scores)
    assert len(cdf) == 5
    assert cdf[0] == 20.0
    assert cdf[-1] == 100.0
    assert all(0.0 <= x <= 100.0 for x in cdf)

    # Against reference distribution
    ref = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    test_scores = np.array([1.5, 9.5, -1.0])
    ref_cdf = scoring.map_empirical_cdf(test_scores, reference_distribution=ref)
    assert ref_cdf[0] == 20.0  # 2 values <= 1.5 in ref
    assert ref_cdf[1] == 100.0
    assert ref_cdf[2] == 0.0


def test_classify_suspicion_level() -> None:
    assert scoring.classify_suspicion_level(None) == "low"
    assert scoring.classify_suspicion_level(89.9) == "low"
    assert scoring.classify_suspicion_level(90.0) == "medium"
    assert scoring.classify_suspicion_level(97.9) == "medium"
    assert scoring.classify_suspicion_level(98.0) == "high"
    assert scoring.classify_suspicion_level(100.0) == "high"


def test_format_reason_codes() -> None:
    row = {
        "z_s_new_accounts": 3.5,
        "s_new_accounts": 0.65,
        "z_s_burst": 2.5,
        "s_burst": 0.80,
        "burst_regularity": True,
        "z_s_bulk": 1.5,
        "s_bulk": 0.12,
        "z_s_inactive": 0.2,  # below threshold
        "s_inactive": 0.10,
    }
    reasons = scoring.format_reason_codes(row, z_threshold=1.0, max_reasons=3)
    assert len(reasons) == 3
    # Sorted by z-score descending: new_accounts first, then burst, then bulk
    assert "65% of new stars are from accounts younger than 30 days" in reasons[0]
    assert "single hour with machine-like inter-arrival regularity" in reasons[1]
    assert "50 or more repositories" in reasons[2]


def test_cosine_similarity() -> None:
    # Exact synthetic overlap
    # overlap = 5, n_a = 10, n_b = 10 -> 5 / sqrt(100) = 0.5
    cos = similarity.compute_cosine_similarity(overlap=5, n_a=10, n_b=10)
    assert pytest.approx(cos, abs=1e-5) == 0.5

    # Identity
    cos_id = similarity.compute_cosine_similarity(overlap=20, n_a=20, n_b=20)
    assert pytest.approx(cos_id, abs=1e-5) == 1.0

    # Disjoint or zero
    assert similarity.compute_cosine_similarity(overlap=0, n_a=10, n_b=10) == 0.0
    assert similarity.compute_cosine_similarity(overlap=5, n_a=0, n_b=10) == 0.0
    assert similarity.compute_cosine_similarity(overlap=-1, n_a=10, n_b=10) == 0.0

    # Asymmetric sizes
    # overlap = 10, n_a = 100, n_b = 400 -> 10 / sqrt(40000) = 10 / 200 = 0.05
    cos_asym = similarity.compute_cosine_similarity(overlap=10, n_a=100, n_b=400)
    assert pytest.approx(cos_asym, abs=1e-5) == 0.05
    assert 0.0 <= cos_asym <= 1.0


def test_retention_reference_loading() -> None:
    if not cohorts.RETENTION_REF_PARQUET.exists():
        pytest.skip("retention reference is a derived file and is not in git")
    ref = cohorts.load_retention_reference()
    assert not ref.empty
    assert "age_bucket" in ref.columns
    assert "fork_median" in ref.columns
    assert "any_median" in ref.columns
    assert len(ref) >= 1
