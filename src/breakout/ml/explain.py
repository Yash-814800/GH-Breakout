"""SHAP explanations and plain-English sentences (Phase 8).

Contributions are TreeSHAP values of the raw booster in log-odds space (positive = pushes the
score up). ``explain_sentence`` turns the top contributions of one row into one sentence using the
``explain_template`` phrases of ``config/feature_dictionary.yaml``: for each feature the ``high``
phrase is used when the row's value is above the training median of that feature and the ``low``
phrase otherwise, so the text always describes the value, whatever the sign of its contribution.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from breakout import features_dict
from breakout import paths as P


def shap_values(booster: Any, X: pd.DataFrame) -> np.ndarray:
    """TreeSHAP contributions, shape ``(n_rows, n_features)``, log-odds space.

    ``X`` must already have the categorical dtypes of the booster (``dataset.apply_categories``).
    """
    import shap

    explainer = shap.TreeExplainer(booster)
    vals = explainer.shap_values(X)
    if isinstance(vals, list):  # older shap: [class0, class1]
        vals = vals[-1]
    return np.asarray(vals)


def top_contributions(
    shap_row: np.ndarray,
    features: Sequence[str],
    n_pos: int = 3,
    n_neg: int = 2,
    skip: set[str] | None = None,
) -> list[tuple[str, float]]:
    """Top ``n_pos`` positive then ``n_neg`` most negative contributions as (name, value)."""
    skip = skip or set()
    order = np.argsort(shap_row)
    pos = [(features[i], float(shap_row[i])) for i in order[::-1] if shap_row[i] > 0]
    neg = [(features[i], float(shap_row[i])) for i in order if shap_row[i] < 0]
    pos = [c for c in pos if c[0] not in skip][:n_pos]
    neg = [c for c in neg if c[0] not in skip][:n_neg]
    return [*pos, *neg]


def _num(v: float, nd: int = 0) -> str:
    if nd == 0:
        return f"{round(v):,}"
    return f"{v:.{nd}f}"


# Features whose ``high`` phrase in the dictionary describes a SMALL value ("only 4 days old",
# "first reply within 3 hours"): the phrase is picked by the opposite comparison with the median.
INVERTED = frozenset({"age_days", "days_since_first_star"})


def _inverted(name: str, entry: Mapping[str, Any]) -> bool:
    return name in INVERTED or entry.get("unit") == "hours"


def format_value(name: str, value: Any, entry: Mapping[str, Any]) -> tuple[str, str]:
    """``(value_text, pct_text)`` for the template tokens ``{value}`` and ``{pct}``."""
    if isinstance(value, str):
        return value, value
    v = float(value)
    unit = entry.get("unit", "")
    pct = f"{v * 100:.0f}%"
    if unit == "share":
        return pct, pct
    if unit == "hours":
        return (f"~{max(1, round(v))}" if v >= 0.5 else "<1"), pct
    if unit in ("ratio", "bits", "gini"):
        return _num(v, 1), pct
    if unit == "score":
        return _num(v, 2), pct
    if entry.get("dtype") == "float" and abs(v) < 10 and v != round(v):
        return _num(v, 1), pct
    return _num(v), pct


def phrase(
    name: str, value: Any, reference: Mapping[str, float], feats: Mapping[str, Any]
) -> str | None:
    """The sentence fragment for one feature, or None when the value is missing."""
    entry = feats[name]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    tpl = entry["explain_template"]
    if isinstance(value, str):
        key = "low" if value in ("Unknown", "Other") else "high"
    else:
        above = float(value) > reference.get(name, 0.0)
        key = "high" if above != _inverted(name, entry) else "low"
    vtxt, ptxt = format_value(name, value, entry)
    return str(tpl[key]).format(value=vtxt, pct=ptxt)


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def explain_sentence(
    row: Mapping[str, Any],
    contribs: Sequence[tuple[str, float]],
    reference: Mapping[str, float],
    feats: Mapping[str, Any] | None = None,
) -> str:
    """One sentence: 'Flagged because ... . Held back by ... .' from the top contributions."""
    feats = feats or features_dict.load()
    up: list[str] = []
    down: list[str] = []
    for name, c in contribs:
        txt = phrase(name, row.get(name), reference, feats)
        if txt is None:
            continue
        (up if c > 0 else down).append(txt)
    out = []
    if up:
        out.append(f"Flagged because {_join(up)}.")
    if down:
        out.append(f"Held back by: {_join(down)}.")
    return " ".join(out) or "No single feature stands out."


def reference_medians(X: pd.DataFrame) -> dict[str, float]:
    """Training medians used to choose the high / low phrase (NaN ignored; categoricals skipped)."""
    out = {}
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ("category", "string", "str"):
            continue
        m = float(np.nanmedian(X[c].to_numpy(dtype=float)))
        out[c] = 0.0 if math.isnan(m) else m
    return out


def global_figures(
    booster: Any,
    X: pd.DataFrame,
    out_dir: Path | None = None,
    n: int = 20000,
    seed: int = 42,
) -> dict[str, Any]:
    """Mean |SHAP| bar chart and a beeswarm on ``n`` sampled rows -> ``reports/figures``."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    out_dir = out_dir or (P.ROOT / "reports" / "figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    Xs = X.sample(n=min(n, len(X)), random_state=seed)
    sv = shap_values(booster, Xs)
    imp = pd.Series(np.abs(sv).mean(axis=0), index=Xs.columns).sort_values(ascending=False)
    top = imp.head(20)[::-1]
    fig, ax = plt.subplots(figsize=(6.5, 5.5), dpi=80)
    ax.barh(top.index, top.values)
    ax.set_xlabel("mean |SHAP| (log-odds)")
    ax.set_title("Global feature importance (top 20)")
    fig.tight_layout()
    bar = out_dir / "shap_importance.png"
    fig.savefig(bar)
    plt.close(fig)
    # beeswarm needs numeric colouring: categoricals as their codes
    Xn = Xs.copy()
    for c in Xn.columns:
        if str(Xn[c].dtype) == "category":
            Xn[c] = Xn[c].cat.codes
    plt.figure(figsize=(7, 6), dpi=80)
    shap.summary_plot(sv, Xn, max_display=15, show=False)
    plt.tight_layout()
    swarm = out_dir / "shap_beeswarm.png"
    plt.savefig(swarm)
    plt.close("all")
    return {"importance": imp.to_dict(), "files": [str(bar), str(swarm)]}
