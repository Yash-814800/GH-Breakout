"""LightGBM training with a time-based inner validation and a seeded config search (Phase 8).

Rules: the inner validation is the last ``inner_validation_months`` of the fold's training
dates, separated from the fitting dates by an embargo of ``embargo_days``; a random validation
split never happens. Negatives are subsampled for fitting (all positives kept); the validation
rows are never sampled, so early stopping and calibration see the real class balance.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from breakout.config import Config
from breakout.ml import dataset as D
from breakout.ml.splits import add_months


def inner_split(
    train_dates: list[date], months: int, embargo_days: int
) -> tuple[list[date], list[date]]:
    """``(fit_dates, val_dates)``: validation = the last ``months`` months of ``train_dates``;
    fit dates end ``embargo_days`` before the validation block starts."""
    ds = sorted(train_dates)
    val_start = add_months(ds[-1], -months) + timedelta(days=1)
    val = [d for d in ds if d >= val_start]
    fit = [d for d in ds if d <= val_start - timedelta(days=embargo_days)]
    if not fit or not val:
        raise ValueError("training dates too short for the inner split")
    return fit, val


def sample_rows(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    """Boolean mask keeping every positive and ``frac`` of the negatives (seeded)."""
    if frac >= 1.0:
        return np.ones(len(y), dtype=bool)
    rng = np.random.default_rng(seed)
    return y.astype(bool) | (rng.random(len(y)) < frac)


def config_grid(cfg: Config, n: int, seed: int) -> list[dict[str, Any]]:
    """``n`` distinct configs drawn without replacement from the grid x scale_pos_weight."""
    m = cfg.model
    keys = list(m.grid)
    combos = [
        {**dict(zip(keys, vals, strict=True)), "scale_pos_weight": spw}
        for vals in itertools.product(*(m.grid[k] for k in keys))
        for spw in m.scale_pos_weight
    ]
    rng = np.random.default_rng(seed)
    pick = rng.permutation(len(combos))[: min(n, len(combos))]
    out = []
    for i in sorted(pick):
        c = dict(combos[i])
        c["num_leaves"] = int(c["num_leaves"])
        c["min_data_in_leaf"] = int(c["min_data_in_leaf"])
        out.append(c)
    return out


def base_params(cfg: Config) -> dict[str, Any]:
    return {
        "objective": "binary",
        "metric": "average_precision",
        "seed": cfg.model.seed,
        "deterministic": True,
        "force_row_wise": True,
        "num_threads": cfg.model.num_threads,
        "verbose": -1,
        "feature_pre_filter": False,
    }


def monotone_vector(cfg: Config, features: list[str], enabled: bool) -> list[int] | None:
    if not enabled:
        return None
    mono = [1 if f in set(cfg.model.monotone_features) else 0 for f in features]
    return mono if any(mono) else None


@dataclass
class FitResult:
    booster: lgb.Booster
    params: dict[str, Any]
    best_iteration: int
    val_ap: float
    trials: list[dict[str, Any]] = field(default_factory=list)


def search_and_fit(
    cfg: Config,
    Xfit: pd.DataFrame,
    yfit: np.ndarray,
    Xval: pd.DataFrame,
    yval: np.ndarray,
    categories: dict[str, list[str]],
    *,
    n_configs: int,
    monotone: bool = False,
    feature_params: dict[str, Any] | None = None,
) -> FitResult:
    """Train one booster per config with early stopping on the validation AP; keep the best.

    The LightGBM datasets are binned once and shared by all configs (``feature_pre_filter`` off).
    """
    Xfit = D.apply_categories(Xfit, categories)
    Xval = D.apply_categories(Xval, categories)
    cats = [c for c in categories if c in Xfit.columns]
    features = list(Xfit.columns)
    ds_params = {"feature_pre_filter": False, "num_threads": cfg.model.num_threads, "verbose": -1}
    dfit = lgb.Dataset(
        Xfit,
        label=yfit.astype(int),
        categorical_feature=cats or "auto",
        params=ds_params,
        free_raw_data=True,
    )
    dval = lgb.Dataset(
        Xval, label=yval.astype(int), reference=dfit, params=ds_params, free_raw_data=True
    )
    mono = monotone_vector(cfg, features, monotone)
    best: FitResult | None = None
    trials = []
    for conf in config_grid(cfg, n_configs, cfg.model.seed):
        params = {**base_params(cfg), **conf, **(feature_params or {})}
        if mono:
            params["monotone_constraints"] = mono
        booster = lgb.train(
            params,
            dfit,
            num_boost_round=cfg.model.max_rounds,
            valid_sets=[dval],
            valid_names=["val"],
            callbacks=[
                lgb.early_stopping(cfg.model.early_stopping_rounds, verbose=False),
            ],
        )
        ap = float(booster.best_score["val"]["average_precision"])
        trials.append({**conf, "best_iteration": booster.best_iteration, "val_ap": ap})
        if best is None or ap > best.val_ap:
            best = FitResult(booster, conf, int(booster.best_iteration), ap)
    assert best is not None
    best.trials = trials
    return best


def predict(booster: lgb.Booster, X: pd.DataFrame, categories: dict[str, list[str]]) -> np.ndarray:
    out = booster.predict(D.apply_categories(X, categories), num_iteration=booster.best_iteration)
    return np.asarray(out, dtype=float)


def val_ap(y: np.ndarray, p: np.ndarray) -> float:
    return float(average_precision_score(y, p))


@dataclass
class FittedModel:
    """A booster, its categories and calibrator (all fitted without test data)."""

    booster: lgb.Booster
    categories: dict[str, list[str]]
    calibrator: Any  # calibrate.Calibrator
    features: list[str]
    result: FitResult
    stats: dict[str, Any]


def fit_calibrated(
    cfg: Config,
    X: pd.DataFrame,
    y: np.ndarray,
    snapshot: np.ndarray,
    train_dates: list[date],
    *,
    n_configs: int,
    monotone: bool = False,
    seed_offset: int = 0,
) -> FittedModel:
    """Inner split of ``train_dates``, negative subsampling, config search, calibrator.

    ``snapshot`` is the datetime64 snapshot date of every row of ``X``. Only rows of
    ``train_dates`` are read.
    """
    from breakout.ml import calibrate as C

    def rows(dates: list[date]) -> np.ndarray:
        return np.flatnonzero(np.isin(snapshot, np.array(sorted(dates), dtype="datetime64[ns]")))

    fit_dates, val_dates = inner_split(
        train_dates, cfg.model.inner_validation_months, cfg.training.embargo_days
    )
    fit_idx, val_idx = rows(fit_dates), rows(val_dates)
    keep = sample_rows(y[fit_idx], cfg.model.negative_sample, cfg.model.seed + seed_offset)
    fit_idx = fit_idx[keep]
    Xf = X.iloc[fit_idx]
    categories = D.fit_categories(Xf)
    res = search_and_fit(
        cfg,
        Xf,
        y[fit_idx],
        X.iloc[val_idx],
        y[val_idx],
        categories,
        n_configs=n_configs,
        monotone=monotone,
    )
    p_val = predict(res.booster, X.iloc[val_idx], categories)
    cal = C.fit_calibrator(p_val, y[val_idx], cfg.model.min_positives_isotonic)
    stats = {
        "fit_dates": [str(min(fit_dates)), str(max(fit_dates))],
        "val_dates": [str(min(val_dates)), str(max(val_dates))],
        "n_fit_rows": int(len(fit_idx)),
        "n_fit_pos": int(y[fit_idx].sum()),
        "n_val_rows": int(len(val_idx)),
        "n_val_pos": int(y[val_idx].sum()),
        "negative_sample": cfg.model.negative_sample,
        "calibrator": cal.kind,
    }
    return FittedModel(res.booster, categories, cal, list(X.columns), res, stats)
