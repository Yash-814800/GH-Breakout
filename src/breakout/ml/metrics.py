"""Ranking and calibration metrics for the per-snapshot candidate lists (Phase 6).

Input frame columns: ``repo_id, snapshot_date, score, label[, prob]``. Everything is computed
per snapshot first (a repo is ranked only against the candidates of its own snapshot) and then
averaged, which handles the same repo appearing on several consecutive snapshots.

Conventions: ``precision@k`` = hits in the top k / k (score ties are broken by ``repo_id``, so it
is deterministic); ``recall@k`` and average precision exist only for snapshots with at least one
positive and are averaged over those; ``precision@k`` is averaged over all snapshots.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def _ranked(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by snapshot, score descending, repo_id ascending (deterministic ties)."""
    return df.sort_values(["snapshot_date", "score", "repo_id"], ascending=[True, False, True])


def per_snapshot(df: pd.DataFrame, k_values: Sequence[int]) -> pd.DataFrame:
    """One row per snapshot: n, n_pos, ap, precision@k, recall@k."""
    rows = []
    for snap, g in _ranked(df).groupby("snapshot_date", sort=True):
        y = g["label"].to_numpy(dtype=bool)
        n_pos = int(y.sum())
        row: dict[str, Any] = {"snapshot_date": snap, "n": len(y), "n_pos": n_pos}
        row["ap"] = (
            float(average_precision_score(y, g["score"].to_numpy())) if n_pos > 0 else math.nan
        )
        for k in k_values:
            hits = int(y[:k].sum())
            row[f"precision@{k}"] = hits / k
            row[f"recall@{k}"] = hits / n_pos if n_pos > 0 else math.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("snapshot_date")


def pooled(df: pd.DataFrame) -> dict[str, float]:
    """PR-AUC (average precision over all rows), ROC-AUC, positive rate and, with ``prob``,
    Brier score, log loss and expected calibration error."""
    y = df["label"].to_numpy(dtype=bool)
    out: dict[str, float] = {
        "n_rows": float(len(y)),
        "n_pos": float(y.sum()),
        "positive_rate": float(y.mean()) if len(y) else math.nan,
    }
    if y.any() and not y.all():
        out["pr_auc"] = float(average_precision_score(y, df["score"].to_numpy()))
        out["roc_auc"] = float(roc_auc_score(y, df["score"].to_numpy()))
    else:
        out["pr_auc"] = out["roc_auc"] = math.nan
    if "prob" in df.columns:
        p = df["prob"].to_numpy(dtype=float)
        out["brier"] = brier(y, p)
        out["log_loss"] = log_loss(y, p)
        out["ece"] = ece(y, p)
    return out


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y.astype(float)) ** 2))


def log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-15) -> float:
    pc = np.clip(p, eps, 1 - eps)
    yy = y.astype(float)
    return float(-np.mean(yy * np.log(pc) + (1 - yy) * np.log(1 - pc)))


def ece(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Expected calibration error with ``n_bins`` equal-count (quantile) bins."""
    n = len(y)
    if n == 0:
        return math.nan
    order = np.argsort(p, kind="stable")
    yy = y.astype(float)[order]
    pp = p[order]
    total = 0.0
    for idx in np.array_split(np.arange(n), n_bins):
        if len(idx):
            total += len(idx) / n * abs(yy[idx].mean() - pp[idx].mean())
    return float(total)


def by_year(snap: pd.DataFrame) -> pd.DataFrame:
    """Mean of the per-snapshot metrics by calendar year of the snapshot (plus snapshot count)."""
    year = pd.to_datetime(snap.index).year
    out = snap.drop(columns=["n", "n_pos"]).groupby(year).mean()
    out.insert(0, "n_snapshots", snap.groupby(year).size())
    out.index.name = "year"
    return out


def block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Moving-block bootstrap: positions 0..n-1 resampled in consecutive blocks of ``block``."""
    block = max(1, min(block, n))
    starts = rng.integers(0, n - block + 1, size=math.ceil(n / block))
    idx = (starts[:, None] + np.arange(block)[None, :]).ravel()
    return idx[:n]


def bootstrap_ci(
    snap: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    n_boot: int = 1000,
    block: int = 4,
    seed: int = 42,
) -> pd.DataFrame:
    """Mean and 95% CI of per-snapshot metrics, block-bootstrapped over snapshot dates.

    Blocks are runs of ``block`` consecutive snapshots (weekly snapshots of the same repos are
    correlated). NaN snapshots (no positives) are ignored per metric.
    """
    cols = list(columns or [c for c in snap.columns if c not in ("n", "n_pos")])
    vals = snap[cols].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    n = len(vals)
    means = np.empty((n_boot, len(cols)))
    for b in range(n_boot):
        means[b] = np.nanmean(vals[block_indices(n, block, rng)], axis=0)
    lo, hi = np.nanpercentile(means, [2.5, 97.5], axis=0)
    mean = np.nanmean(vals, axis=0)
    return pd.DataFrame({"mean": mean, "ci_low": lo, "ci_high": hi}, index=cols)


def _weighted_ap(y: np.ndarray, w: np.ndarray, tie_end: np.ndarray) -> float:
    """Average precision of rows already sorted by score (descending), with row weights ``w``.

    ``tie_end`` marks the last row of every group of equal scores, so tied rows enter together
    (the same step function as scikit-learn's ``average_precision_score``).
    """
    wy = w * y
    tp = np.cumsum(wy)[tie_end]
    n = np.cumsum(w)[tie_end]
    gain = np.diff(np.concatenate([[0.0], tp]))
    total = tp[-1]
    if total == 0:
        return math.nan
    prec = np.divide(tp, n, out=np.zeros_like(tp), where=n > 0)
    return float(np.sum(gain * prec) / total)


def bootstrap_pooled_pr_auc(
    df: pd.DataFrame, *, n_boot: int = 1000, block: int = 4, seed: int = 42
) -> dict[str, float]:
    """Pooled PR-AUC with a 95% CI from the same block bootstrap over snapshot dates.

    The rows are sorted once; a resample is a vector of snapshot multiplicities used as row weights.
    """
    d = df.sort_values("score", ascending=False, kind="stable")
    snaps = np.sort(d["snapshot_date"].unique())
    pos = pd.Index(snaps).get_indexer(d["snapshot_date"])
    y = d["label"].to_numpy(dtype=float)
    s = d["score"].to_numpy()
    tie_end = np.concatenate([s[1:] != s[:-1], [True]])
    point = _weighted_ap(y, np.ones(len(y)), tie_end)
    rng = np.random.default_rng(seed)
    aps = np.empty(n_boot)
    for b in range(n_boot):
        mult = np.bincount(block_indices(len(snaps), block, rng), minlength=len(snaps))
        aps[b] = _weighted_ap(y, mult[pos].astype(float), tie_end)
    lo, hi = np.nanpercentile(aps, [2.5, 97.5])
    return {"pr_auc": point, "ci_low": float(lo), "ci_high": float(hi)}


def lead_time_report(preds: pd.DataFrame, labels: pd.DataFrame, k: int = 25) -> dict[str, Any]:
    """Lead time of our flag versus the first GitHub Trending appearance.

    ``preds``: ``repo_id, snapshot_date, score``. ``labels``: ``repo_id, snapshot_date,
    first_trending_date, trending_covered``. Population: repos with ``trending_covered`` rows whose
    earliest ``first_trending_date`` is not null (the repo appeared on an all-languages list
    within 60 days of a snapshot). First flag date = the earliest snapshot at which the repo was in
    the top ``k`` of its snapshot; lead = first_trending_date - first_flag_date in days (positive
    = we were earlier). The resolution is one snapshot (weekly in backtests): a flag can be
    visible up to 7 days later than the moment the repo first qualified.
    """
    ranked = _ranked(preds)
    ranked["rank"] = ranked.groupby("snapshot_date").cumcount() + 1
    flags = ranked[ranked["rank"] <= k].groupby("repo_id")["snapshot_date"].min().rename("flag")
    cov = labels[labels["trending_covered"] & labels["first_trending_date"].notna()]
    first_tr = pd.to_datetime(cov.groupby("repo_id")["first_trending_date"].min()).rename("trend")
    pop = first_tr.to_frame().join(pd.to_datetime(flags), how="left")
    lead = (pop["trend"] - pop["flag"]).dt.days.dropna()
    n = len(pop)
    return {
        "k": k,
        "n_trending_repos": n,
        "n_flagged": int(lead.size),
        "share_never_flagged": float(pop["flag"].isna().mean()) if n else math.nan,
        "share_flagged_before_trending": float((lead > 0).sum() / n) if n else math.nan,
        "share_flagged_7d_before": float((lead >= 7).sum() / n) if n else math.nan,
        "median_lead_days": float(lead.median()) if lead.size else math.nan,
        "iqr_lead_days": [float(lead.quantile(0.25)), float(lead.quantile(0.75))]
        if lead.size
        else [math.nan, math.nan],
        "snapshot_resolution": "weekly",
    }
