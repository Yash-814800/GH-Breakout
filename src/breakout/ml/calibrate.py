"""Probability calibration (Phase 8): isotonic regression, Platt scaling for small samples.

A calibrator is fitted on predictions of data the booster did not train on and is stored as JSON
(isotonic breakpoints or Platt coefficients), so no pickle is needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from breakout.ml import metrics as M

EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


@dataclass
class Calibrator:
    kind: str  # 'isotonic' | 'platt' | 'identity'
    x: list[float] | None = None  # isotonic X_thresholds_
    y: list[float] | None = None  # isotonic y_thresholds_
    coef: float | None = None  # Platt slope on logit(score)
    intercept: float | None = None

    def predict(self, score: np.ndarray) -> np.ndarray:
        s = np.asarray(score, dtype=float)
        if self.kind == "isotonic":
            assert self.x is not None and self.y is not None
            return np.clip(np.interp(s, self.x, self.y), EPS, 1.0)
        if self.kind == "platt":
            assert self.coef is not None and self.intercept is not None
            z = self.coef * _logit(s) + self.intercept
            return 1.0 / (1.0 + np.exp(-z))
        return s

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_json(cls, d: dict[str, Any] | str) -> Calibrator:
        data: dict[str, Any] = json.loads(d) if isinstance(d, str) else d
        return cls(**data)


def fit_calibrator(score: np.ndarray, y: np.ndarray, min_positives: int = 200) -> Calibrator:
    """Isotonic regression of ``y`` on ``score``; Platt scaling below ``min_positives``."""
    s = np.asarray(score, dtype=float)
    yy = np.asarray(y, dtype=float)
    n_pos = int(yy.sum())
    if n_pos == 0 or n_pos == len(yy):
        return Calibrator("identity")
    if n_pos < min_positives:
        lr = LogisticRegression(C=1e6, max_iter=1000)
        lr.fit(_logit(s).reshape(-1, 1), yy.astype(int))
        return Calibrator("platt", coef=float(lr.coef_[0, 0]), intercept=float(lr.intercept_[0]))
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip", increasing=True)
    iso.fit(s, yy)
    return Calibrator(
        "isotonic",
        x=[float(v) for v in iso.X_thresholds_],
        y=[float(v) for v in iso.y_thresholds_],
    )


def reliability_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Equal-count bins: mean predicted, observed rate and counts (as in ``metrics.ece``)."""
    order = np.argsort(p, kind="stable")
    yy = np.asarray(y, dtype=float)[order]
    pp = np.asarray(p, dtype=float)[order]
    rows = []
    for i, idx in enumerate(np.array_split(np.arange(len(yy)), n_bins)):
        if len(idx):
            rows.append(
                {
                    "bin": i + 1,
                    "n": len(idx),
                    "n_pos": int(yy[idx].sum()),
                    "mean_pred": float(pp[idx].mean()),
                    "observed": float(yy[idx].mean()),
                }
            )
    return pd.DataFrame(rows)


def calibration_summary(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    yy = np.asarray(y, dtype=bool)
    pp = np.asarray(p, dtype=float)
    return {"brier": M.brier(yy, pp), "log_loss": M.log_loss(yy, pp), "ece": M.ece(yy, pp)}
