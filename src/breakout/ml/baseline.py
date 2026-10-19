"""Simple velocity baselines and the Phase 6 baseline report.

B1 = 7-day star velocity (ties by 1-day stars), B2 = velocity relative to size, B3 = acceleration.
Every later model must beat B1 on PR-AUC and precision@k (CLAUDE.md section 6).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ml import metrics as M
from breakout.ml.splits import Fold, make_folds

log = get_logger(__name__)

REPORT = P.ROOT / "reports" / "baseline.md"
METRICS_JSON = P.ROOT / "reports" / "metrics" / "baseline.json"
FIG_DIR = P.ROOT / "reports" / "figures"

ScoreFn = Callable[[pd.DataFrame], pd.Series]

BASELINES: dict[str, ScoreFn] = {
    # stars_1d <= stars_7d < 1000 (candidates have < max_stars_total stars), so /1000 only breaks ties
    "B1": lambda d: d["stars_7d"] + d["stars_1d"] / 1000.0,
    "B2": lambda d: d["stars_7d"] / (d["stars_total_before"] + 10.0),
    "B3": lambda d: (d["stars_7d"] - d["stars_prev_7d"]).astype(float),
}
DESCRIPTIONS = {
    "B1": "stars in the last 7 days (ties: last day)",
    "B2": "7-day stars / (stars so far + 10)",
    "B3": "7-day stars minus the 7 days before",
}


def folds_for(cfg: Config, dates: list[date]) -> list[Fold]:
    t = cfg.training
    return make_folds(
        dates,
        test_window_months=t.test_window_months,
        embargo_days=t.embargo_days,
        min_train_years=t.min_train_years,
        horizon_days=cfg.labels.horizon_days,
    )


def fit_isotonic(train: pd.DataFrame, score: pd.Series) -> IsotonicRegression:
    """Monotone map score -> P(breakout), fitted on the fold's training rows only."""
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip", increasing=True)
    iso.fit(score.to_numpy(dtype=float), train["label"].to_numpy(dtype=float))
    return iso


def run_baselines(df: pd.DataFrame, folds: list[Fold]) -> dict[str, pd.DataFrame]:
    """Out-of-sample predictions of every baseline: ``repo_id, snapshot_date, score, label[, prob]``.

    ``df`` needs the dbt columns plus ``label``. B1 also gets an isotonic ``prob`` fitted on each
    fold's training dates (rows with those snapshot dates), applied to the fold's test rows.
    """
    out: dict[str, list[pd.DataFrame]] = {b: [] for b in BASELINES}
    snap = pd.to_datetime(df["snapshot_date"]).dt.date
    for i, f in enumerate(folds):
        test = df[snap.isin(set(f.test_dates))]
        train = df[snap.isin(set(f.train_dates))]
        for name, fn in BASELINES.items():
            part = test[["repo_id", "snapshot_date", "label"]].copy()
            part["score"] = fn(test)
            part["fold"] = i
            if name == "B1":
                iso = fit_isotonic(train, fn(train))
                part["prob"] = iso.predict(part["score"].to_numpy(dtype=float))
            out[name].append(part)
    return {b: pd.concat(parts, ignore_index=True) for b, parts in out.items()}


def evaluate(
    preds: dict[str, pd.DataFrame],
    labels: pd.DataFrame,
    k_values: list[int],
    *,
    n_boot: int = 1000,
    block: int = 4,
) -> dict[str, Any]:
    """All report numbers for every baseline (per snapshot, by year, pooled, CIs, lead time)."""
    res: dict[str, Any] = {}
    for name, p in preds.items():
        snap = M.per_snapshot(p, k_values)
        ci = M.bootstrap_ci(snap, n_boot=n_boot, block=block)
        pooled = M.pooled(p)
        pooled_ci = M.bootstrap_pooled_pr_auc(p, n_boot=n_boot, block=block)
        res[name] = {
            "snapshot": snap,
            "by_year": M.by_year(snap),
            "ci": ci,
            "pooled": pooled,
            "pooled_pr_auc_ci": pooled_ci,
            "lead_time": M.lead_time_report(
                p[["repo_id", "snapshot_date", "score"]],
                labels,
                k=25 if 25 in k_values else k_values[0],
            ),
        }
    return res


def fold_table(
    folds: list[Fold], preds: dict[str, pd.DataFrame], k_values: list[int]
) -> pd.DataFrame:
    k = 25 if 25 in k_values else k_values[0]
    rows = []
    for i, f in enumerate(folds):
        row: dict[str, Any] = {
            "fold": i,
            "test_start": f.test_start,
            "test_end": f.test_end,
            "train_snaps": len(f.train_dates),
            "test_snaps": len(f.test_dates),
        }
        for name, p in preds.items():
            pf = p[p["fold"] == i]
            snap = M.per_snapshot(pf, [k])
            row["test_pos"] = int(pf["label"].sum())
            row[f"{name} PR-AUC"] = M.pooled(pf)["pr_auc"]
            row[f"{name} P@{k}"] = snap[f"precision@{k}"].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def sanity_tables(df: pd.DataFrame, dates: list[date], n: int = 10) -> dict[date, pd.DataFrame]:
    """Top-``n`` B1-ranked candidates on each date with the realized gain and label."""
    out = {}
    snap = pd.to_datetime(df["snapshot_date"]).dt.date
    for d in dates:
        g = df[snap == d].copy()
        g["score"] = BASELINES["B1"](g)
        g = g.sort_values(["score", "repo_id"], ascending=[False, True]).head(n)
        out[d] = g[
            ["repo_name_at_D", "stars_7d", "stars_1d", "stars_total_before", "gain_30d", "label"]
        ]
    return out


def pick_sanity_dates(dates: list[date]) -> list[date]:
    """Three spread-out historical snapshot dates (25%, 50%, 85% of the matured range)."""
    ds = sorted(dates)
    return [ds[int(len(ds) * q)] for q in (0.25, 0.5, 0.85)]


# ---------------------------------------------------------------- report


def _fmt(x: float, nd: int = 3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def _md_table(df: pd.DataFrame, nd: int = 3) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in df.astype(object).itertuples(index=False):
        cells = [_fmt(v, nd) if isinstance(v, float) else str(v) for v in r]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def make_figures(preds: dict[str, pd.DataFrame], res: dict[str, Any], k: int) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, ax = plt.subplots(figsize=(5, 4), dpi=90)
    for name, p in preds.items():
        prec, rec, _ = precision_recall_curve(
            p["label"].to_numpy(dtype=bool), p["score"].to_numpy()
        )
        step = max(1, len(rec) // 2000)
        ax.plot(rec[::step], prec[::step], label=f"{name} (AP {res[name]['pooled']['pr_auc']:.3f})")
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title("Baselines: pooled PR curve (test folds)")
    ax.legend()
    fig.tight_layout()
    f1 = FIG_DIR / "baseline_pr_curve.png"
    fig.savefig(f1)
    plt.close(fig)
    paths.append(f1)

    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=90)
    years = sorted(set().union(*[set(r["by_year"].index) for r in res.values()]))
    width = 0.8 / len(res)
    for j, (name, r) in enumerate(res.items()):
        vals = [r["by_year"][f"precision@{k}"].get(y, np.nan) for y in years]
        ax.bar(np.arange(len(years)) + j * width, vals, width, label=name)
    ax.set_xticks(np.arange(len(years)) + width)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel(f"precision@{k}")
    ax.set_title(f"Baselines: precision@{k} by year (mean over snapshots)")
    ax.legend()
    fig.tight_layout()
    f2 = FIG_DIR / "baseline_precision_by_year.png"
    fig.savefig(f2)
    plt.close(fig)
    paths.append(f2)
    return paths


def render_report(
    cfg: Config,
    folds: list[Fold],
    preds: dict[str, pd.DataFrame],
    res: dict[str, Any],
    sanity: dict[date, pd.DataFrame],
    n_boot: int,
) -> str:
    ks = cfg.training.k_values
    k = 25 if 25 in ks else ks[0]
    t = cfg.training
    L = [
        "# Baseline evaluation (Phase 6)",
        "",
        "Every later model must beat **B1** on PR-AUC and precision@k to be promoted.",
        "",
        "## Setup",
        "",
        f"- Candidates: age <= {cfg.candidates.max_age_days} d, < {cfg.candidates.max_stars_total} stars "
        f"before D, >= {cfg.candidates.min_stars_14d} stars in [D-14, D), no forks / mirrors / bot owners.",
        f"- Label (primary): `breakout_rel` = 30-day gain >= max({cfg.labels.relative_floor_gain}, "
        f"{cfg.labels.relative_quantile:.3f} quantile of the candidates on that snapshot).",
        f"- Rolling-origin, expanding window: test blocks of {t.test_window_months} months, "
        f"first block after {t.min_train_years} years, embargo {t.embargo_days} days. "
        f"{len(folds)} folds; test snapshots {folds[0].test_start} .. {folds[-1].test_end}.",
        f"- Data: GH Archive trusted era (events before {cfg.history.trusted_end + timedelta(days=1)}).",
        f"- Confidence intervals: block bootstrap over snapshot dates ({n_boot} resamples, blocks of 4 weeks).",
        "- precision@k = hits in top k / k per snapshot, averaged over all snapshots; recall@k and AP are "
        "averaged over snapshots with at least one positive. Ties are broken by repo_id.",
        "",
        "Baselines:",
        "",
    ]
    L += [f"- **{b}**: {DESCRIPTIONS[b]}" for b in BASELINES]
    L += ["", "## Folds", "", _md_table(fold_table(folds, preds, ks)), ""]
    L += ["## Pooled test metrics (all folds)", ""]
    rows = []
    for b, r in res.items():
        p, c = r["pooled"], r["ci"]
        row: dict[str, Any] = {
            "baseline": b,
            "PR-AUC [95% CI]": f"{p['pr_auc']:.4f} [{r['pooled_pr_auc_ci']['ci_low']:.4f}, "
            f"{r['pooled_pr_auc_ci']['ci_high']:.4f}]",
            "ROC-AUC": _fmt(p["roc_auc"], 4),
            "mean AP": f"{c.loc['ap', 'mean']:.3f} [{c.loc['ap', 'ci_low']:.3f}, {c.loc['ap', 'ci_high']:.3f}]",
        }
        for kk in ks:
            row[f"P@{kk}"] = (
                f"{c.loc[f'precision@{kk}', 'mean']:.3f} "
                f"[{c.loc[f'precision@{kk}', 'ci_low']:.3f}, {c.loc[f'precision@{kk}', 'ci_high']:.3f}]"
            )
        for kk in ks:
            row[f"R@{kk}"] = _fmt(c.loc[f"recall@{kk}", "mean"], 3)
        rows.append(row)
    pr = res["B1"]["pooled"]
    L += [_md_table(pd.DataFrame(rows)), ""]
    L += [
        f"Test rows {int(pr['n_rows']):,}, positives {int(pr['n_pos']):,} "
        f"(positive rate {pr['positive_rate']:.4%}).",
        "",
        "### Calibration of B1 (isotonic, fitted on each fold's training dates)",
        "",
        f"Brier {pr['brier']:.5f}, log loss {pr['log_loss']:.5f}, ECE (10 quantile bins) {pr['ece']:.5f}.",
        "",
        "## Per year (mean over the year's test snapshots)",
        "",
    ]
    for b, r in res.items():
        by = r["by_year"].reset_index()
        keep = ["year", "n_snapshots", "ap"] + [f"precision@{kk}" for kk in ks]
        L += [f"**{b}**", "", _md_table(by[keep]), ""]
    L += ["## Lead time versus GitHub Trending", ""]
    lt_rows = []
    for b, r in res.items():
        lt = r["lead_time"]
        lt_rows.append(
            {
                "baseline": b,
                "trending repos": lt["n_trending_repos"],
                f"flagged (top-{lt['k']})": lt["n_flagged"],
                "never flagged": _fmt(lt["share_never_flagged"], 3),
                "flagged before Trending": _fmt(lt["share_flagged_before_trending"], 3),
                ">= 7 d before": _fmt(lt["share_flagged_7d_before"], 3),
                "median lead (d)": _fmt(lt["median_lead_days"], 1),
                "IQR (d)": f"{_fmt(lt['iqr_lead_days'][0], 1)} .. {_fmt(lt['iqr_lead_days'][1], 1)}",
            }
        )
    L += [
        "Population: repos that appeared on an all-languages GitHub Trending list within 60 days of a "
        "test snapshot whose window has Trending coverage (>= 54 of 60 days). First flag = earliest "
        f"snapshot in which the repo ranked in the top {k}; snapshot resolution is weekly, so a flag is "
        "visible at most 7 days late. Positive lead = we flagged before Trending; a repo flagged only "
        "after it trended counts as not early.",
        "",
        _md_table(pd.DataFrame(lt_rows)),
        "",
        "## Figures",
        "",
        "![PR curve](figures/baseline_pr_curve.png)",
        "",
        "![precision by year](figures/baseline_precision_by_year.png)",
        "",
        "## Sanity check: top 10 B1-ranked candidates on three historical dates",
        "",
        "`gain_30d` is the realized gain in [D, D+30); `label` is `breakout_rel`.",
        "",
    ]
    for d, tbl in sanity.items():
        L += [f"**{d}**", "", _md_table(tbl.reset_index(drop=True), 0), ""]
    return "\n".join(L)


def _jsonable(o: Any) -> Any:
    if isinstance(o, pd.DataFrame):
        return json.loads(o.reset_index().to_json(orient="records", date_format="iso"))
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, list | tuple):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def run(cfg: Config, labels_file: Path | None = None, n_boot: int = 1000) -> dict[str, Any]:
    """Load the exported table, run the baselines over the folds and write the report + JSON."""
    from breakout.ml import labels_export as le

    df = le.load_labels(labels_file)
    df["label"] = df["breakout_rel"].astype(bool)
    dates = sorted(pd.to_datetime(df["snapshot_date"]).dt.date.unique())
    folds = folds_for(cfg, dates)
    log.info("%d rows, %d snapshots, %d folds", len(df), len(dates), len(folds))
    preds = run_baselines(df, folds)
    trend_cols = df[["repo_id", "snapshot_date", "first_trending_date", "trending_covered"]]
    in_test = set().union(*[set(f.test_dates) for f in folds])
    trend_cols = trend_cols[pd.to_datetime(trend_cols["snapshot_date"]).dt.date.isin(in_test)]
    res = evaluate(preds, trend_cols, cfg.training.k_values, n_boot=n_boot)
    sanity = sanity_tables(df, pick_sanity_dates(sorted(in_test)))
    figs = make_figures(preds, res, 25 if 25 in cfg.training.k_values else cfg.training.k_values[0])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(cfg, folds, preds, res, sanity, n_boot) + "\n")
    payload = {b: {k: v for k, v in r.items() if k != "snapshot"} for b, r in res.items()}
    METRICS_JSON.write_text(json.dumps(_jsonable(payload), indent=2) + "\n")
    log.info("wrote %s, %s, %s", REPORT, METRICS_JSON, [f.name for f in figs])
    return payload
