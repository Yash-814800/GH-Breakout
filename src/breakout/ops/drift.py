"""Feature drift monitoring using Population Stability Index (PSI) (§9.3 Step 4, §9.6).

Calculates PSI per feature comparing the last 4 weeks of live features against the champion's
training distribution using 10 quantile bins from training.
Flags any feature with PSI > 0.25 as high drift.
Writes `data/derived/ops/drift.json` (and `derived/ops/drift.json` on the derived repo).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from breakout import paths as P
from breakout.config import Config, get_config
from breakout.features_dict import load as load_features_dict
from breakout.logging import get_logger
from breakout.ml import dataset as D
from breakout.ml import registry as G

log = get_logger(__name__)

OPS_DIR = P.DERIVED_DIR / "ops"
DRIFT_REPORT_PATH = OPS_DIR / "drift.json"
HF_PREFIX = "ops"
DRIFT_THRESHOLD = 0.25


def calculate_psi(
    expected: np.ndarray,
    actual: np.ndarray,
    num_bins: int = 10,
    epsilon: float = 1e-4,
) -> float:
    """Calculate Population Stability Index (PSI) between expected (training) and actual (live)."""
    # Filter out NaNs for bin calculation
    exp_valid = expected[~np.isnan(expected)]
    act_valid = actual[~np.isnan(actual)]

    if len(exp_valid) == 0 or len(act_valid) == 0:
        return 0.0

    # Determine quantile bins from expected distribution
    quantiles = np.linspace(0, 1, num_bins + 1)
    bin_edges = np.percentile(exp_valid, quantiles * 100)
    # Ensure strictly increasing bins by adding tiny jitter if duplicated
    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return 0.0

    # Expand outer boundaries to cover all potential actual values
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    # Calculate frequencies in each bin
    exp_counts, _ = np.histogram(exp_valid, bins=bin_edges)
    act_counts, _ = np.histogram(act_valid, bins=bin_edges)

    # Convert to proportions with smoothing epsilon
    exp_pct = exp_counts / len(exp_valid) + epsilon
    act_pct = act_counts / len(act_valid) + epsilon

    # Normalize back to 1
    exp_pct = exp_pct / exp_pct.sum()
    act_pct = act_pct / act_pct.sum()

    # PSI formula: sum((Actual - Expected) * ln(Actual / Expected))
    psi_val = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi_val)


def calculate_categorical_psi(
    expected: pd.Series,
    actual: pd.Series,
    epsilon: float = 1e-4,
) -> float:
    """Calculate PSI for categorical features based on category frequencies."""
    all_cats = list(set(expected.dropna().unique()).union(set(actual.dropna().unique())))
    if not all_cats:
        return 0.0

    exp_counts = expected.value_counts(normalize=True)
    act_counts = actual.value_counts(normalize=True)

    exp_pct = np.array([exp_counts.get(c, 0.0) + epsilon for c in all_cats])
    act_pct = np.array([act_counts.get(c, 0.0) + epsilon for c in all_cats])

    exp_pct = exp_pct / exp_pct.sum()
    act_pct = act_pct / act_pct.sum()

    psi_val = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi_val)


def find_recent_live_features(
    as_of: date,
    window_days: int = 28,
) -> pd.DataFrame | None:
    """Load live feature rows scored in [as_of - window_days, as_of]."""
    live_dir_new = P.DERIVED_DIR / "live" / "features"
    live_dir_old = P.DERIVED_DIR / "live"
    files: list[Path] = []

    start_d = as_of - timedelta(days=window_days)

    if live_dir_new.exists():
        for p in live_dir_new.glob("date=*.parquet"):
            try:
                d_str = p.stem.split("=")[-1]
                d = date.fromisoformat(d_str)
                if start_d <= d <= as_of:
                    files.append(p)
            except Exception:
                continue

    if not files and live_dir_old.exists():
        for p in live_dir_old.glob("features_*.parquet"):
            try:
                d_str = p.stem.replace("features_", "")
                d = date.fromisoformat(d_str)
                if start_d <= d <= as_of:
                    files.append(p)
            except Exception:
                continue

    if not files:
        return None

    frames = [pd.read_parquet(f) for f in files]
    return pd.concat(frames, ignore_index=True)


def compute_drift(
    cfg: Config | None = None,
    as_of: date | None = None,
    upload: bool = False,
) -> dict[str, Any]:
    """Compute PSI for all live features and write derived/ops/drift.json."""
    cfg = cfg or get_config(None)
    now = datetime.now(UTC)
    as_of_d = as_of or now.date()

    champion = G.load_champion(cfg)
    feats = load_features_dict()
    live_feats = champion.features

    # Load training distribution (champion's training data)
    X_train, _, _ = D.load_training(features=live_feats)

    # Load live features from last 4 weeks
    live_df = find_recent_live_features(as_of_d, window_days=28)

    psi_results: dict[str, float] = {}
    high_drift: list[str] = []

    if live_df is not None and not live_df.empty:
        for feat in live_feats:
            if feat not in live_df.columns or feat not in X_train.columns:
                continue
            fd_entry = feats.get(feat, {})
            dtype = fd_entry.get("dtype", "")

            if dtype in ("category", "string") or feat in champion.categories:
                val = calculate_categorical_psi(X_train[feat], live_df[feat])
            else:
                s_train = pd.to_numeric(X_train[feat], errors="coerce").to_numpy(dtype=float)
                s_live = pd.to_numeric(live_df[feat], errors="coerce").to_numpy(dtype=float)
                val = calculate_psi(s_train, s_live)

            psi_results[feat] = round(val, 4)
            if val > DRIFT_THRESHOLD:
                high_drift.append(feat)
    else:
        log.warning("No recent live features found for drift calculation as of %s", as_of_d)

    report = {
        "computed_at": now.isoformat(timespec="seconds"),
        "as_of": as_of_d.isoformat(),
        "model_version": champion.version,
        "n_live_features": len(live_feats),
        "n_recent_rows": len(live_df) if live_df is not None else 0,
        "high_drift_threshold": DRIFT_THRESHOLD,
        "high_drift_features": sorted(high_drift),
        "psi_by_feature": psi_results,
    }

    OPS_DIR.mkdir(parents=True, exist_ok=True)
    DRIFT_REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    log.info(
        "Wrote drift report to %s (%d high drift features)",
        DRIFT_REPORT_PATH,
        len(high_drift),
    )

    if upload:
        from breakout.lake import hf

        api = hf.get_api()
        item = hf.UploadItem(DRIFT_REPORT_PATH, f"{HF_PREFIX}/drift.json")
        hf.put_small_files(api, cfg, "derived", [item], "Update feature drift report")

    return report
