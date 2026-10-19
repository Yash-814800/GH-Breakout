"""Rolling-origin cross-validation of the LightGBM model (Phase 8).

One *variant* is a feature subset plus a search size. Every fold writes a shard
(``data/derived/ml/cv/<variant>/fold=NN.parquet`` + ``.json``), so the run is resumable and
idempotent; ``oof_predictions`` concatenates the shards of a variant.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from breakout import features_dict
from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ml import calibrate as C
from breakout.ml import dataset as D
from breakout.ml import train as T
from breakout.ml.baseline import folds_for
from breakout.ml.splits import Fold

log = get_logger(__name__)


def ml_dir():
    return P.DATA_DIR / "derived" / "ml"


def cv_dir(variant: str):
    return ml_dir() / "cv" / variant


@dataclass(frozen=True)
class Variant:
    name: str
    features: list[str]
    n_configs: int
    monotone: bool = False
    permute_labels: bool = False  # sanity check (a): train on within-snapshot shuffled labels


def variants(cfg: Config) -> dict[str, Variant]:
    """All CV variants. ``full`` is the champion candidate; the others are cheaper (ablations)."""
    d = features_dict.load()
    live = D.feature_columns(live_only=True)

    def where(pred) -> list[str]:
        return [f for f in live if pred(d[f])]

    cheap = cfg.model.ablation_n_configs
    out = [
        Variant("full", live, cfg.model.search_n_configs),
        Variant("full_monotone", live, cfg.model.search_n_configs, monotone=True),
        Variant("abl_full_cheap", live, cheap),
        Variant("abl_tier_A", where(lambda e: e["tier"] == "A"), cheap),
        Variant("abl_tier_AB", where(lambda e: e["tier"] in ("A", "B")), cheap),
        Variant("abl_no_tastemaker", where(lambda e: e["group"] != "tastemaker"), cheap),
        Variant("abl_no_stargazers", where(lambda e: e["group"] != "stargazers"), cheap),
        Variant("abl_star_dynamics_only", where(lambda e: e["group"] == "star_dynamics"), cheap),
        Variant("sanity_stars7d_only", ["stars_7d"], cheap),
        Variant("sanity_permuted", live, 1, permute_labels=True),
    ]
    return {v.name: v for v in out}


def _permute_within_snapshot(y: np.ndarray, snaps: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = y.copy()
    for s in np.unique(snaps):
        idx = np.flatnonzero(snaps == s)
        out[idx] = y[rng.permutation(idx)]
    return out


def run_fold(
    cfg: Config,
    v: Variant,
    i: int,
    f: Fold,
    X: pd.DataFrame,
    y: np.ndarray,
    meta: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    t0 = time.time()
    sd = meta["snapshot_date"].to_numpy()

    def rows(dates) -> np.ndarray:
        return np.flatnonzero(np.isin(sd, np.array(sorted(dates), dtype="datetime64[ns]")))

    fit_dates, val_dates = T.inner_split(
        list(f.train_dates), cfg.model.inner_validation_months, cfg.training.embargo_days
    )
    fit_idx, val_idx, test_idx = rows(fit_dates), rows(val_dates), rows(f.test_dates)
    y_fit, y_val = y[fit_idx], y[val_idx]
    if v.permute_labels:
        y_fit = _permute_within_snapshot(y_fit, sd[fit_idx], cfg.model.seed + i)
        y_val = _permute_within_snapshot(y_val, sd[val_idx], cfg.model.seed + i)
    keep = T.sample_rows(y_fit, cfg.model.negative_sample, cfg.model.seed + i)
    fit_idx, y_fit = fit_idx[keep], y_fit[keep]
    Xf = X.iloc[fit_idx]
    categories = D.fit_categories(Xf)
    res = T.search_and_fit(
        cfg,
        Xf,
        y_fit,
        X.iloc[val_idx],
        y_val,
        categories,
        n_configs=v.n_configs,
        monotone=v.monotone,
    )
    p_val = T.predict(res.booster, X.iloc[val_idx], categories)
    cal = C.fit_calibrator(p_val, y_val, cfg.model.min_positives_isotonic)
    p_test = T.predict(res.booster, X.iloc[test_idx], categories)
    shard = pd.DataFrame(
        {
            "repo_id": meta["repo_id"].to_numpy()[test_idx],
            "snapshot_date": meta["snapshot_date"].to_numpy()[test_idx],
            "fold": i,
            "raw_score": p_test,
            "prob_calibrated": cal.predict(p_test),
            "label": y[test_idx],
            "gain_30d": meta["gain_30d"].to_numpy()[test_idx],
        }
    )
    info = {
        "fold": i,
        "variant": v.name,
        "test_start": str(f.test_start),
        "n_fit_rows": int(len(fit_idx)),
        "n_fit_pos": int(y_fit.sum()),
        "n_val_rows": int(len(val_idx)),
        "n_val_pos": int(y_val.sum()),
        "n_test_rows": int(len(test_idx)),
        "n_test_pos": int(y[test_idx].sum()),
        "best_params": res.params,
        "best_iteration": res.best_iteration,
        "val_ap": res.val_ap,
        "calibrator": cal.kind,
        "trials": res.trials,
        "seconds": round(time.time() - t0, 1),
    }
    return shard, info


def run_variant(
    cfg: Config,
    v: Variant,
    X: pd.DataFrame,
    y: np.ndarray,
    meta: pd.DataFrame,
    folds: list[Fold],
    only_folds: list[int] | None = None,
) -> None:
    out = cv_dir(v.name)
    out.mkdir(parents=True, exist_ok=True)
    Xv = X[v.features]
    for i, f in enumerate(folds):
        if only_folds is not None and i not in only_folds:
            continue
        shard_path = out / f"fold={i:02d}.parquet"
        if shard_path.exists():
            continue
        shard, info = run_fold(cfg, v, i, f, Xv, y, meta)
        shard.to_parquet(shard_path, index=False)
        (out / f"fold={i:02d}.json").write_text(json.dumps(info, indent=1, default=str) + "\n")
        log.info(
            "%s fold %d/%d: %s s, val AP %.4f, iter %d, test pos %d",
            v.name,
            i + 1,
            len(folds),
            info["seconds"],
            info["val_ap"],
            info["best_iteration"],
            info["n_test_pos"],
        )


def load_oof(variant: str) -> pd.DataFrame:
    parts = sorted(cv_dir(variant).glob("fold=*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no CV shards for {variant}")
    return pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)


def load_fold_info(variant: str) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(cv_dir(variant).glob("fold=*.json"))]


def write_oof(variant: str = "full") -> Any:
    """``data/derived/ml/oof_predictions.parquet`` from the shards of ``variant``."""
    df = load_oof(variant)
    path = ml_dir() / "oof_predictions.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    return path


def run(cfg: Config, names: list[str], only_folds: list[int] | None = None) -> None:
    allv = variants(cfg)
    unknown = [n for n in names if n not in allv]
    if unknown:
        raise ValueError(f"unknown variants {unknown}; choose from {sorted(allv)}")
    X, y_s, meta = D.load_training()
    y = y_s.to_numpy()
    dates = D.snapshot_dates(meta)
    folds = folds_for(cfg, dates)
    log.info("%d rows, %d folds, variants %s", len(y), len(folds), names)
    for n in names:
        run_variant(cfg, allv[n], X, y, meta, folds, only_folds)
