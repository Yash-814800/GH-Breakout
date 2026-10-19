"""Daily versus weekly scoring check (Phase 8, deliverable 11).

The model trains on Monday snapshots. This builds *daily* snapshots for the last four weeks of the
holdout with the history SQL (on a copy of the warehouse, ``features.build.run_features_range``),
scores them with the evaluation model (trained without these dates) and compares calibration and
precision@k by weekday.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from breakout import paths as P
from breakout.config import Config
from breakout.features.build import LABEL_COLUMNS
from breakout.logging import get_logger
from breakout.ml import baseline as B
from breakout.ml import calibrate as C
from breakout.ml import metrics as M
from breakout.ml import registry as G

log = get_logger(__name__)

RANGE_FILE = P.DERIVED_DIR / "ml" / "daily_range.parquet"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def export_range(warehouse: Path, start: date, end: date, out: Path | None = None) -> Path:
    """Features + labels of the daily snapshots ``start..end`` from the range warehouse copy."""
    out = out or RANGE_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        con.execute("SET memory_limit='2GB'")
        con.execute("SET threads=1")
        lab = ", ".join(f"l.{c}" for c in LABEL_COLUMNS)
        con.execute(
            f"""COPY (SELECT f.*, {lab} FROM mart_repo_features f
                      JOIN mart_labels l USING (repo_id, snapshot_date)
                      WHERE f.snapshot_date BETWEEN DATE '{start}' AND DATE '{end}'
                      ORDER BY f.snapshot_date, f.repo_id)
                TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)"""
        )
    finally:
        con.close()
    return out


def evaluate(cfg: Config, version: str, path: Path | None = None) -> dict[str, Any]:
    """Score the daily range with the evaluation model of ``version``; metrics by weekday."""
    ks = cfg.training.k_values
    k = 25 if 25 in ks else ks[0]
    df = pd.read_parquet(path or RANGE_FILE)
    model = G.load_model(G.models_dir() / version / "eval_model")
    pred = G.predict(model, df, explain=False)
    d = pd.DataFrame(
        {
            "repo_id": df["repo_id"].to_numpy(),
            "snapshot_date": pd.to_datetime(df["snapshot_date"]).to_numpy(),
            "score": pred["raw_score"].to_numpy(),
            "prob": pred["prob"].to_numpy(),
            "label": df["breakout_rel"].astype(bool).to_numpy(),
        }
    )
    base = df.assign(stars_prev_7d=df["stars_7d"] - df["star_accel_7d"])
    b1 = d.assign(score=B.BASELINES["B1"](base).to_numpy())
    wd = pd.to_datetime(d["snapshot_date"]).dt.dayofweek
    rows = []
    per_snap = M.per_snapshot(d, ks)
    per_snap_b1 = M.per_snapshot(b1, ks)
    snap_wd = pd.to_datetime(per_snap.index).dayofweek
    for w in range(7):
        m = (wd == w).to_numpy()
        if not m.any():
            continue
        sub = d[m]
        sm = snap_wd == w
        exp, obs = float(sub["prob"].sum()), float(sub["label"].sum())
        rows.append(
            {
                "weekday": WEEKDAYS[w],
                "snapshots": int(sm.sum()),
                "rows": int(m.sum()),
                "positives": int(obs),
                "PR-AUC": M.pooled(sub)["pr_auc"],
                f"P@{k}": float(per_snap[f"precision@{k}"][sm].mean()),
                f"B1 P@{k}": float(per_snap_b1[f"precision@{k}"][sm].mean()),
                "expected positives": exp,
                "observed/expected": obs / exp if exp > 0 else float("nan"),
            }
        )
    table = pd.DataFrame(rows)
    mon = snap_wd == 0
    col = f"precision@{k}"
    diff = per_snap[col][mon].mean() - per_snap[col][~mon].mean()
    # bootstrap over snapshot days (units are days; the difference is Monday minus other days)
    rng = np.random.default_rng(42)
    pm, po = per_snap[col][mon].to_numpy(), per_snap[col][~mon].to_numpy()
    boots = [rng.choice(pm, len(pm)).mean() - rng.choice(po, len(po)).mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    is_mon = (wd == 0).to_numpy()
    ratio = {
        "monday": float(d["label"][is_mon].sum() / d["prob"][is_mon].sum()),
        "other": float(d["label"][~is_mon].sum() / d["prob"][~is_mon].sum()),
    }
    res = {
        "version": version,
        "dates": [str(d["snapshot_date"].min().date()), str(d["snapshot_date"].max().date())],
        "n_snapshots": int(per_snap.shape[0]),
        "by_weekday": json.loads(table.to_json(orient="records")),
        "p_at_k_monday_minus_other": {
            "diff": float(diff),
            "ci_low": float(lo),
            "ci_high": float(hi),
        },
        "observed_over_expected": ratio,
        "ece_all": C.calibration_summary(d["label"].to_numpy(), d["prob"].to_numpy())["ece"],
        "pooled": M.pooled(d.assign()),
    }
    res["markdown"] = render(res, table, k)
    return res


def render(res: dict[str, Any], table: pd.DataFrame, k: int) -> str:
    from breakout.ml.baseline import _md_table

    p = res["p_at_k_monday_minus_other"]
    r = res["observed_over_expected"]
    return "\n".join(
        [
            f"Daily snapshots {res['dates'][0]} .. {res['dates'][1]} ({res['n_snapshots']} days) scored with the evaluation model "
            f"of `{res['version']}` (trained without these dates), features and labels from the history SQL on a warehouse copy.",
            "",
            _md_table(table),
            "",
            f"- Mean precision@{k}: Mondays minus other days {p['diff']:+.3f} [{p['ci_low']:+.3f}, {p['ci_high']:+.3f}] (bootstrap over days).",
            f"- Observed / expected positives (calibration): Mondays {r['monday']:.2f}, other days {r['other']:.2f} (1.00 = perfectly calibrated).",
            f"- Calibrated-probability ECE over all days: {res['ece_all']:.5f}.",
            "- With 4-5 snapshots per weekday each cell is noisy; the comparison that matters is Monday versus the rest.",
        ]
    )


def run(cfg: Config, version: str) -> Path:
    res = evaluate(cfg, version)
    out = P.ROOT / "reports" / "metrics" / "daily_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(B._jsonable(res), indent=2, default=str) + "\n")
    return out
