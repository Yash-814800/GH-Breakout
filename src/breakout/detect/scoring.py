"""Robust scoring, empirical CDF calibration, and reason codes for suspicious growth."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Documented equal signal weights summing to 1.0 (Phase 11, §11.1)
DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    "s_new_accounts": 1.0 / 6.0,
    "s_inactive": 1.0 / 6.0,
    "s_bulk": 1.0 / 6.0,
    "s_burst": 1.0 / 6.0,
    "s_lockstep": 1.0 / 6.0,
    "s_no_engagement": 1.0 / 6.0,
}

MAD_CONSISTENCY_FACTOR: float = 1.4826  # Normal distribution scale factor
MEAN_DEV_SCALE_FACTOR: float = 1.2533  # Normal mean absolute deviation scale


def robust_zscore(
    x: float | np.ndarray,
    med: float,
    mad: float,
    fallback_mad: float | None = None,
    clip_min: float = 0.0,
    clip_max: float = 6.0,
) -> float | np.ndarray:
    """Compute robust z-score: (x - median) / (1.4826 * MAD), clipped to [0, 6].

    If MAD is 0 (e.g. sparse signals where >50% values are 0), uses fallback_mad
    (mean absolute deviation * 1.2533) to prevent division by zero while preserving
    sensitivity to non-zero outliers.
    """
    scale = MAD_CONSISTENCY_FACTOR * mad
    if scale < 1e-5 and fallback_mad is not None:
        scale = fallback_mad
    if scale < 1e-5:
        # Constant signal across candidates on snapshot date
        if isinstance(x, np.ndarray):
            return np.zeros_like(x, dtype=float)
        return 0.0

    z = (x - med) / scale
    return np.clip(z, clip_min, clip_max)


def compute_signals_zscores(
    df: pd.DataFrame,
    signal_cols: list[str] | None = None,
    group_col: str | None = "snapshot_date",
) -> pd.DataFrame:
    """Compute robust z-scores for signal columns, grouped by snapshot_date."""
    cols = signal_cols or list(DEFAULT_SIGNAL_WEIGHTS.keys())
    active_cols = [c for c in cols if c in df.columns]
    res = df.copy()

    for col in active_cols:
        z_col = f"z_{col}"
        if group_col and group_col in df.columns and df[group_col].nunique() > 1:
            z_vals = np.zeros(len(df), dtype=float)
            for _, idx in df.groupby(group_col).groups.items():
                vals = df.loc[idx, col].to_numpy(dtype=float)
                med = float(np.nanmedian(vals)) if len(vals) > 0 else 0.0
                abs_dev = np.abs(vals - med)
                mad = float(np.nanmedian(abs_dev)) if len(vals) > 0 else 0.0
                mean_dev = (
                    float(np.nanmean(abs_dev)) * MEAN_DEV_SCALE_FACTOR if len(vals) > 0 else 0.0
                )
                z_vals[idx] = robust_zscore(vals, med, mad, fallback_mad=mean_dev)
            res[z_col] = z_vals
        else:
            vals = df[col].to_numpy(dtype=float)
            med = float(np.nanmedian(vals)) if len(vals) > 0 else 0.0
            abs_dev = np.abs(vals - med)
            mad = float(np.nanmedian(abs_dev)) if len(vals) > 0 else 0.0
            mean_dev = float(np.nanmean(abs_dev)) * MEAN_DEV_SCALE_FACTOR if len(vals) > 0 else 0.0
            res[z_col] = robust_zscore(vals, med, mad, fallback_mad=mean_dev)

    return res


def compute_weighted_raw_score(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> np.ndarray:
    """Calculate the weighted sum of robust z-scores."""
    w_map = weights or DEFAULT_SIGNAL_WEIGHTS
    available_signals = [col for col in w_map if f"z_{col}" in df.columns]
    if not available_signals:
        return np.zeros(len(df), dtype=float)

    total_weight = sum(w_map[col] for col in available_signals)
    raw = np.zeros(len(df), dtype=float)
    for col in available_signals:
        normalized_w = w_map[col] / total_weight
        raw += normalized_w * df[f"z_{col}"].to_numpy(dtype=float)
    return raw


def map_empirical_cdf(
    scores: np.ndarray | pd.Series,
    reference_distribution: np.ndarray | None = None,
) -> np.ndarray:
    """Map raw scores to 0-100 via empirical CDF of reference (historical) scores."""
    arr = np.asarray(scores, dtype=float)
    if len(arr) == 0:
        return np.array([], dtype=float)

    if reference_distribution is not None and len(reference_distribution) > 0:
        ref_sorted = np.sort(np.asarray(reference_distribution, dtype=float))
        # Percentile rank against reference empirical CDF
        ranks = np.searchsorted(ref_sorted, arr, side="right")
        pct = (ranks / len(ref_sorted)) * 100.0
        return np.round(np.clip(pct, 0.0, 100.0), 1)

    # In-sample percentile rank
    ranks = pd.Series(arr).rank(pct=True, method="max").to_numpy(dtype=float)
    return np.round(ranks * 100.0, 1)


def classify_suspicion_level(score: float | None) -> str:
    """Classify into low/medium/high at 90th and 98th percentiles (Phase 11, §11.1)."""
    if score is None or np.isnan(score):
        return "low"
    if score >= 98.0:
        return "high"
    if score >= 90.0:
        return "medium"
    return "low"


def format_reason_codes(
    row: dict[str, Any] | pd.Series,
    z_threshold: float = 1.0,
    max_reasons: int = 3,
) -> list[str]:
    """Generate up to 3 non-accusatory, human-readable reason strings."""
    reasons: list[tuple[float, str]] = []

    # 1. New accounts
    z_new = float(row.get("z_s_new_accounts", 0.0) or 0.0)
    val_new = float(row.get("s_new_accounts", 0.0) or 0.0)
    if z_new >= z_threshold and val_new > 0.15:
        pct = round(val_new * 100)
        reasons.append((z_new, f"{pct}% of new stars are from accounts younger than 30 days"))

    # 2. Inactive accounts
    z_inact = float(row.get("z_s_inactive", 0.0) or 0.0)
    val_inact = float(row.get("s_inactive", 0.0) or 0.0)
    if z_inact >= z_threshold and val_inact > 0.25:
        pct = round(val_inact * 100)
        reasons.append(
            (z_inact, f"{pct}% of stargazers had zero activity in the 90 days before starring")
        )

    # 3. Bulk starrers
    z_bulk = float(row.get("z_s_bulk", 0.0) or 0.0)
    val_bulk = float(row.get("s_bulk", 0.0) or 0.0)
    if z_bulk >= z_threshold and val_bulk > 0.05:
        pct = round(val_bulk * 100)
        reasons.append(
            (z_bulk, f"{pct}% of stargazers starred 50 or more repositories on that same day")
        )

    # 4. Burst hour
    z_burst = float(row.get("z_s_burst", 0.0) or 0.0)
    val_burst = float(row.get("s_burst", 0.0) or 0.0)
    if z_burst >= z_threshold and val_burst > 0.35:
        pct = round(val_burst * 100)
        regularity = row.get("burst_regularity", False)
        extra = " with machine-like inter-arrival regularity" if regularity else ""
        reasons.append(
            (z_burst, f"{pct}% of the 14-day window's stars arrived in a single hour{extra}")
        )

    # 5. Lockstep rings
    z_lock = float(row.get("z_s_lockstep", 0.0) or 0.0)
    val_lock = float(row.get("s_lockstep", 0.0) or 0.0)
    if z_lock >= z_threshold and val_lock > 0.05:
        pct = round(val_lock * 100)
        reasons.append(
            (
                z_lock,
                f"{pct}% of stargazers co-starred 3+ identical repos in lockstep within 24 hours",
            )
        )

    # 6. Low code engagement
    z_eng = float(row.get("z_s_no_engagement", 0.0) or 0.0)
    val_eng = float(row.get("s_no_engagement", 0.0) or 0.0)
    if z_eng >= z_threshold and val_eng > 0.8:
        reasons.append(
            (z_eng, "Rapid star velocity with near-zero code engagement (forks, issues, PRs)")
        )

    # Sort by z-score descending and return top max_reasons
    reasons.sort(key=lambda item: item[0], reverse=True)
    return [r[1] for r in reasons[:max_reasons]]
