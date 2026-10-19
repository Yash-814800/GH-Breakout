"""Training-table loader for the model (Phase 8).

``load_training`` reads ``data/derived/training/features_labels`` through DuckDB with a bounded
memory limit and returns float32 features, the primary label and a metadata frame. Categorical
columns stay strings here; ``fit_categories`` / ``apply_categories`` fix their levels from a
training fold and map unseen values to 'Other'.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from breakout import features_dict
from breakout import paths as P

CATEGORICAL = ("primary_language", "owner_type")
META_COLUMNS = ["repo_id", "snapshot_date", "gain_30d", "first_trending_date", "trending_covered"]
# never allowed as model inputs (keys and label-derived columns)
FORBIDDEN = frozenset(
    {
        "repo_id",
        "snapshot_date",
        "bucket",
        "year",
        "repo_name",
        "repo_name_at_D",
        "gain_30d",
        "threshold_rel",
        "breakout_rel",
        "breakout_abs",
        "days_to_threshold",
        "first_trending_date",
        "trending_covered",
    }
)
OTHER = "Other"


def training_dir() -> Path:
    return P.DATA_DIR / "derived" / "training" / "features_labels"


def feature_columns(live_only: bool = True) -> list[str]:
    feats = features_dict.model_features(features_dict.load(), live_only=live_only)
    assert_feature_list(feats)
    return feats


def assert_feature_list(cols: Sequence[str]) -> None:
    bad = sorted(set(cols) & FORBIDDEN)
    if bad:
        raise AssertionError(f"keys / label columns used as features: {bad}")


def load_training(
    years: Sequence[int] | None = None,
    features: Sequence[str] | None = None,
    path: Path | None = None,
    label: str = "breakout_rel",
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """``(X, y, meta)`` of the matured training rows. Floats are float32; ``y`` is bool."""
    feats = list(features) if features is not None else feature_columns()
    assert_feature_list(feats)
    root = path or training_dir()
    all_years = sorted(int(d.name.split("=")[1]) for d in root.glob("year=*"))
    chosen = [y for y in all_years if not years or y in set(years)]
    if not chosen:
        raise ValueError("no training rows found")
    sel = []
    for c in dict.fromkeys([*feats, *META_COLUMNS, label]):
        if c in CATEGORICAL or c in (
            "repo_id",
            "snapshot_date",
            "first_trending_date",
            "trending_covered",
            label,
        ):
            sel.append(c)
        else:
            sel.append(f"CAST({c} AS FLOAT) AS {c}")
    # one year at a time: categorical strings become pandas categories immediately (memory)
    xs: list[pd.DataFrame] = []
    ms: list[pd.DataFrame] = []
    ys: list[pd.Series] = []
    for yr in chosen:
        con = duckdb.connect()
        con.execute("SET memory_limit='1500MB'")
        con.execute("SET threads=1")
        try:
            part = con.execute(
                f"SELECT {', '.join(sel)} FROM read_parquet('{root}/year={yr}/part-0.parquet') "
                "ORDER BY snapshot_date, repo_id"
            ).df()
        finally:
            con.close()
        for c in CATEGORICAL:
            if c in part.columns:
                part[c] = part[c].astype(str).astype("category")
        xs.append(part[feats])
        ms.append(part[META_COLUMNS])
        ys.append(part[label].astype(bool))
        del part
    X = pd.concat(xs, ignore_index=True)
    del xs
    meta = pd.concat(ms, ignore_index=True)
    meta["snapshot_date"] = pd.to_datetime(meta["snapshot_date"])
    y = pd.concat(ys, ignore_index=True)
    assert y.notna().all(), "unmatured (NULL) labels in the training table"
    return X, y, meta


def fit_categories(X: pd.DataFrame) -> dict[str, list[str]]:
    """Levels of every categorical column present in ``X`` (sorted, with 'Other' last)."""
    out = {}
    for c in CATEGORICAL:
        if c in X.columns:
            levels = sorted({str(v) for v in X[c].dropna().unique()} - {OTHER})
            out[c] = [*levels, OTHER]
    return out


def apply_categories(X: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Copy of ``X`` with categorical columns as pandas ``category`` with the fixed levels."""
    X = X.copy()
    for c, levels in categories.items():
        if c not in X.columns:
            continue
        s = X[c].astype(object).where(X[c].isin(levels), OTHER)
        X[c] = pd.Categorical(s, categories=levels)
    return X


def snapshot_dates(meta: pd.DataFrame) -> list:
    return sorted(meta["snapshot_date"].dt.date.unique())


def to_float32(X: pd.DataFrame) -> pd.DataFrame:
    num = [c for c in X.columns if c not in CATEGORICAL]
    X = X.copy()
    X[num] = X[num].astype(np.float32)
    return X
