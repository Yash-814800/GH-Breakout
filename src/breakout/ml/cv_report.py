"""Evaluation of the CV shards and ``reports/model_cv.md`` (Phase 8)."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ml import baseline as B
from breakout.ml import calibrate as C
from breakout.ml import cv
from breakout.ml import dataset as D
from breakout.ml import metrics as M
from breakout.ml.baseline import _fmt, _md_table
from breakout.ml.splits import Fold

log = get_logger(__name__)

REPORT = P.ROOT / "reports" / "model_cv.md"
METRICS_JSON = P.ROOT / "reports" / "metrics" / "model_cv.json"
DAILY_JSON = P.ROOT / "reports" / "metrics" / "daily_check.json"
FIG_DIR = P.ROOT / "reports" / "figures"
BASE_FEATURES = ["stars_7d", "stars_1d", "stars_total_before", "star_accel_7d"]
SLICE_FEATURES = ["primary_language", "detail_coverage_28d", "era_post_2025_10"]


def _key(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def baseline_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(base, meta)``: the columns the velocity baselines read, and the Trending meta."""
    X, y, meta = D.load_training(features=[*BASE_FEATURES])
    base = pd.concat([meta[["repo_id", "snapshot_date"]], X], axis=1)
    base["stars_prev_7d"] = base["stars_7d"] - base["star_accel_7d"]
    return base, meta


def predictions(variant: str, base: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Model and baselines on the same rows: ``repo_id, snapshot_date, score, label, fold[, prob]``."""
    o = _key(cv.load_oof(variant))
    m = o.merge(_key(base), on=["repo_id", "snapshot_date"], how="left", validate="1:1")
    if m["stars_7d"].isna().any():
        raise AssertionError("OOF rows without baseline inputs")
    out = {}
    model = m[["repo_id", "snapshot_date", "fold", "label"]].copy()
    model["score"] = m["raw_score"]
    model["prob"] = m["prob_calibrated"]
    out["model"] = model
    for name, fn in B.BASELINES.items():
        p = m[["repo_id", "snapshot_date", "fold", "label"]].copy()
        p["score"] = fn(m)
        out[name] = p
    return out


def summarize(p: pd.DataFrame, ks: list[int]) -> dict[str, Any]:
    snap = M.per_snapshot(p, ks)
    pooled = M.pooled(p)
    return {
        "pr_auc": pooled["pr_auc"],
        "roc_auc": pooled["roc_auc"],
        "ap": float(snap["ap"].mean()),
        **{f"precision@{k}": float(snap[f"precision@{k}"].mean()) for k in ks},
        "n_pos": pooled["n_pos"],
    }


def promotion_rule(
    cand: pd.DataFrame, ref: pd.DataFrame, ks: list[int], n_boot: int, k: int = 25
) -> dict[str, Any]:
    """Candidate vs reference on identical rows: PR-AUC and mean P@k differences with paired CIs.

    ``beats`` = both point differences > 0 and neither CI lies entirely below 0.
    """
    d_pr = M.bootstrap_pooled_pr_auc_diff(cand, ref, n_boot=n_boot)
    sa, sb = M.per_snapshot(cand, ks), M.per_snapshot(ref, ks)
    col = f"precision@{k}"
    d_p = M.paired_snapshot_diff(sa, sb, [col], n_boot=n_boot).loc[col]
    beats = (
        d_pr["diff"] > 0 and d_p["mean"] > 0 and d_pr["ci_high"] > 0 and float(d_p["ci_high"]) > 0
    )
    return {
        "pr_auc_diff": d_pr,
        f"p@{k}_diff": {
            "diff": float(d_p["mean"]),
            "ci_low": float(d_p["ci_low"]),
            "ci_high": float(d_p["ci_high"]),
        },
        "beats": bool(beats),
    }


def slice_table(
    model: pd.DataFrame, b1: pd.DataFrame, key: pd.Series, name: str, min_pos: int = 20
) -> pd.DataFrame:
    """Pooled PR-AUC / ROC-AUC of the model and B1 within each level of ``key`` (rows ranked together)."""
    rows = []
    for level, idx in key.groupby(key, observed=True).groups.items():
        m, b = model.loc[idx], b1.loc[idx]
        if m["label"].sum() < min_pos:
            continue
        pm, pb = M.pooled(m), M.pooled(b)
        rows.append(
            {
                name: level,
                "rows": len(m),
                "positives": int(m["label"].sum()),
                "model PR-AUC": pm["pr_auc"],
                "B1 PR-AUC": pb["pr_auc"],
                "model ROC-AUC": pm["roc_auc"],
                "B1 ROC-AUC": pb["roc_auc"],
            }
        )
    return pd.DataFrame(rows)


def coverage_bucket(v: pd.Series) -> pd.Series:
    out = pd.Series("none (0)", index=v.index, dtype=object)
    out[v.isna()] = "NULL (spine only)"
    out[(v > 0) & (v < 1)] = "partial (0, 1)"
    out[v >= 1] = "full (1)"
    return out


def figures(preds: dict[str, pd.DataFrame], by_year: dict[str, pd.DataFrame], k: int) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, ax = plt.subplots(figsize=(5, 4), dpi=80)
    for name in ("model", "B1"):
        p = preds[name]
        prec, rec, _ = precision_recall_curve(p["label"].to_numpy(bool), p["score"].to_numpy())
        step = max(1, len(rec) // 2000)
        ax.plot(rec[::step], prec[::step], label=f"{name} (AP {M.pooled(p)['pr_auc']:.3f})")
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title("Pooled PR curve, test folds")
    ax.legend()
    fig.tight_layout()
    f = FIG_DIR / "cv_pr_curve.png"
    fig.savefig(f)
    plt.close(fig)
    paths.append(str(f))

    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=80)
    years = sorted(by_year["model"].index)
    w = 0.8 / len(by_year)
    for j, (name, by) in enumerate(by_year.items()):
        ax.bar(
            np.arange(len(years)) + j * w,
            [by[f"precision@{k}"].get(y, np.nan) for y in years],
            w,
            label=name,
        )
    ax.set_xticks(np.arange(len(years)) + w)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_ylabel(f"precision@{k}")
    ax.set_title(f"precision@{k} by year")
    ax.legend(fontsize=7)
    fig.tight_layout()
    f = FIG_DIR / "cv_precision_by_year.png"
    fig.savefig(f)
    plt.close(fig)
    paths.append(str(f))

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8), dpi=80)
    m = preds["model"]
    y = m["label"].to_numpy(bool)
    for ax, col, title in ((axes[0], "score", "raw score"), (axes[1], "prob", "calibrated")):
        t = C.reliability_table(y, m[col].to_numpy())
        ax.loglog(t["mean_pred"].clip(lower=1e-5), t["observed"].clip(lower=1e-5), "o-")
        lim = [1e-5, 1]
        ax.plot(lim, lim, "k--", lw=0.8)
        ax.set_xlabel("mean predicted")
        ax.set_ylabel("observed rate")
        ax.set_title(f"Reliability: {title}")
    fig.tight_layout()
    f = FIG_DIR / "cv_reliability.png"
    fig.savefig(f)
    plt.close(fig)
    paths.append(str(f))
    return paths


def _row(name: str, s: dict[str, Any], ks: list[int]) -> dict[str, Any]:
    return {
        "variant": name,
        "PR-AUC": _fmt(s["pr_auc"], 4),
        "ROC-AUC": _fmt(s["roc_auc"], 3),
        "mean AP": _fmt(s["ap"], 3),
        **{f"P@{k}": _fmt(s[f"precision@{k}"], 3) for k in ks},
    }


def run(cfg: Config, n_boot: int | None = None) -> dict[str, Any]:
    nb = n_boot or cfg.model.n_boot
    ks = cfg.training.k_values
    k = 25 if 25 in ks else ks[0]
    base, meta = baseline_inputs()
    preds = predictions("full", base)
    trend = _key(meta[["repo_id", "snapshot_date", "first_trending_date", "trending_covered"]])
    test_keys = _key(preds["model"][["repo_id", "snapshot_date"]])
    trend = trend.merge(test_keys, on=["repo_id", "snapshot_date"])
    res = B.evaluate(preds, trend, ks, n_boot=nb)
    dates = sorted(pd.to_datetime(meta["snapshot_date"]).dt.date.unique())
    folds: list[Fold] = B.folds_for(cfg, dates)
    infos = cv.load_fold_info("full")

    out: dict[str, Any] = {"k": k, "n_boot": nb}
    out["main"] = {
        n: {
            "pooled": r["pooled"],
            "pooled_pr_auc_ci": r["pooled_pr_auc_ci"],
            "ci": r["ci"],
            "lead_time": r["lead_time"],
        }
        for n, r in res.items()
    }
    vs = {b: promotion_rule(preds["model"], preds[b], ks, nb, k) for b in ("B1", "B2", "B3")}
    out["vs_baselines"] = vs

    # per-fold table
    ft = []
    for i, f in enumerate(folds):
        row: dict[str, Any] = {"fold": i, "test_start": f.test_start, "test_end": f.test_end}
        sub = {n: p[p["fold"] == i] for n, p in preds.items() if n in ("model", "B1")}
        row["test_pos"] = int(sub["model"]["label"].sum())
        for n, p in sub.items():
            row[f"{n} PR-AUC"] = M.pooled(p)["pr_auc"]
            row[f"{n} P@{k}"] = M.per_snapshot(p, [k])[f"precision@{k}"].mean()
        inf = next((x for x in infos if x["fold"] == i), None)
        row["iter"] = inf["best_iteration"] if inf else None
        row["cal"] = inf["calibrator"] if inf else None
        ft.append(row)
    fold_df = pd.DataFrame(ft)

    # ablations & sanity
    abl_names = [
        "abl_tier_A",
        "abl_tier_AB",
        "abl_full_cheap",
        "abl_no_tastemaker",
        "abl_no_stargazers",
        "abl_star_dynamics_only",
    ]
    abl: dict[str, Any] = {}
    cheap = None
    for name in ["abl_full_cheap", *[a for a in abl_names if a != "abl_full_cheap"]]:
        try:
            pr = predictions(name, base)["model"]
        except FileNotFoundError:
            continue
        s = summarize(pr, ks)
        entry: dict[str, Any] = {"summary": s, "complete": pr["fold"].nunique() == len(folds)}
        if name == "abl_full_cheap":
            cheap = pr
        elif cheap is not None:
            common = cheap.merge(pr[["repo_id", "snapshot_date"]], on=["repo_id", "snapshot_date"])
            a = pr.merge(common[["repo_id", "snapshot_date"]], on=["repo_id", "snapshot_date"])
            entry["vs_full_cheap"] = promotion_rule(a, common, ks, max(200, nb // 4), k)
        abl[name] = entry
    out["ablations"] = abl

    san: dict[str, Any] = {}
    perm = None
    try:
        perm = predictions("sanity_permuted", base)["model"]
        ps = M.pooled(perm)
        thr = cfg.model.permutation_tolerance * ps["positive_rate"]
        san["permuted_training"] = {
            "pr_auc": ps["pr_auc"],
            "positive_rate": ps["positive_rate"],
            "threshold": thr,
            "passed": bool(ps["pr_auc"] < thr),
        }
    except FileNotFoundError:
        pass
    # permuting the model's OOF labels within each snapshot (metric machinery check)
    mp = preds["model"].copy()
    mp["label"] = cv._permute_within_snapshot(
        mp["label"].to_numpy(), mp["snapshot_date"].to_numpy(), 7
    )
    pm = M.pooled(mp)
    san["permuted_test_labels"] = {
        "pr_auc": pm["pr_auc"],
        "positive_rate": pm["positive_rate"],
        "passed": bool(pm["pr_auc"] < cfg.model.permutation_tolerance * pm["positive_rate"]),
    }
    try:
        s7 = predictions("sanity_stars7d_only", base)["model"]
        san["stars7d_only"] = {
            "pr_auc": M.pooled(s7)["pr_auc"],
            f"p@{k}": float(M.per_snapshot(s7, [k])[f"precision@{k}"].mean()),
            "b1_pr_auc": res["B1"]["pooled"]["pr_auc"],
            "b1_p": float(res["B1"]["snapshot"][f"precision@{k}"].mean()),
        }
    except FileNotFoundError:
        pass
    out["sanity"] = san
    failed = [
        n
        for n in ("permuted_training", "permuted_test_labels")
        if n in san and not san[n]["passed"]
    ]
    if failed:
        raise AssertionError(f"sanity check failed: {failed} (see {METRICS_JSON})")

    # monotone
    try:
        mono = predictions("full_monotone", base)["model"]
        r = promotion_rule(mono, preds["model"], ks, max(200, nb // 4), k)
        s_m, s_f = summarize(mono, ks), summarize(preds["model"], ks)
        keep = s_m["pr_auc"] >= s_f["pr_auc"] and s_m[f"precision@{k}"] >= s_f[f"precision@{k}"]
        out["monotone"] = {
            "summary": s_m,
            "vs_full": r,
            "keep": bool(keep),
            "complete": mono["fold"].nunique() == len(folds),
        }
    except FileNotFoundError:
        pass

    # slices
    sl = _key(meta[["repo_id", "snapshot_date"]])
    Xs, _, _ = D.load_training(features=SLICE_FEATURES)
    sl = pd.concat([sl, Xs], axis=1)
    keyed = preds["model"][["repo_id", "snapshot_date"]].merge(
        sl, on=["repo_id", "snapshot_date"], how="left"
    )
    keyed.index = preds["model"].index
    langs = keyed["primary_language"].astype(str)
    top = langs[~langs.isin(["Unknown", "Other"])].value_counts().head(10).index
    lang_key = langs.where(langs.isin([*top, "Unknown", "Other"]), "Other")
    out["slices"] = {}
    slices = {
        "language": lang_key,
        "detail coverage": coverage_bucket(keyed["detail_coverage_28d"]),
        "era_post_2025_10": keyed["era_post_2025_10"].astype(int),
    }
    tables = {n: slice_table(preds["model"], preds["B1"], key, n) for n, key in slices.items()}
    for n, t in tables.items():
        out["slices"][n] = json.loads(t.to_json(orient="records"))

    # calibration
    yv = preds["model"]["label"].to_numpy(bool)
    cal = {
        "raw": C.calibration_summary(yv, preds["model"]["score"].to_numpy()),
        "calibrated": C.calibration_summary(yv, preds["model"]["prob"].to_numpy()),
        "reliability_calibrated": json.loads(
            C.reliability_table(yv, preds["model"]["prob"].to_numpy()).to_json(orient="records")
        ),
        "reliability_raw": json.loads(
            C.reliability_table(yv, preds["model"]["score"].to_numpy()).to_json(orient="records")
        ),
    }
    out["calibration"] = cal
    figs = figures(preds, {"model": res["model"]["by_year"], "B1": res["B1"]["by_year"]}, k)

    daily = json.loads(DAILY_JSON.read_text()) if DAILY_JSON.exists() else None
    out["daily_check"] = daily
    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.write_text(json.dumps(B._jsonable(out), indent=2, default=str) + "\n")
    REPORT.write_text(render(cfg, out, res, fold_df, tables, infos, folds, figs, nb) + "\n")
    log.info("wrote %s", REPORT)
    return out


def render(cfg, out, res, fold_df, tables, infos, folds, figs, nb) -> str:  # noqa: PLR0913
    ks = cfg.training.k_values
    k = out["k"]
    t = cfg.training
    m = cfg.model
    L = [
        "# Model evaluation: LightGBM vs velocity baselines (Phase 8)",
        "",
        "Rolling-origin CV with the Phase 6 folds and metrics (`breakout ml cv`); every number is out-of-fold. "
        "The baselines are scored on exactly the same rows.",
        "",
        "## Setup",
        "",
        f"- Label `breakout_rel`; folds: expanding window, {t.test_window_months}-month test blocks, embargo {t.embargo_days} days, "
        f"{len(folds)} folds, test snapshots {folds[0].test_start} .. {folds[-1].test_end}.",
        f"- Features: the {len(D.feature_columns())} live-available allowed features (`config/feature_dictionary.yaml`); LightGBM, "
        f"seed {m.seed}, deterministic, {m.num_threads} thread.",
        f"- Per fold: the last {m.inner_validation_months} months of the training dates (after an embargo of {t.embargo_days} days) are the inner "
        f"validation set for early stopping (AP) and for the calibrator; {m.search_n_configs} configs of the grid x `scale_pos_weight` {m.scale_pos_weight} are "
        f"tried and the best inner-validation AP wins. Negatives are subsampled to {m.negative_sample:.0%} for fitting (all positives kept); the validation rows are not sampled, so the calibrator is fitted on real-balance data.",
        f"- CIs: block bootstrap over snapshot dates ({nb} resamples, 4-week blocks); differences are paired (same resamples).",
        "",
        "## Folds (model vs B1)",
        "",
        _md_table(fold_df),
        "",
        "## Pooled test metrics",
        "",
    ]
    rows = []
    for n, r in res.items():
        p, c = r["pooled"], r["ci"]
        row = {
            "": n,
            "PR-AUC [95% CI]": f"{p['pr_auc']:.4f} [{r['pooled_pr_auc_ci']['ci_low']:.4f}, {r['pooled_pr_auc_ci']['ci_high']:.4f}]",
            "ROC-AUC": _fmt(p["roc_auc"], 3),
            "mean AP": f"{c.loc['ap', 'mean']:.3f} [{c.loc['ap', 'ci_low']:.3f}, {c.loc['ap', 'ci_high']:.3f}]",
        }
        for kk in ks:
            row[f"P@{kk}"] = (
                f"{c.loc[f'precision@{kk}', 'mean']:.3f} [{c.loc[f'precision@{kk}', 'ci_low']:.3f}, {c.loc[f'precision@{kk}', 'ci_high']:.3f}]"
            )
        for kk in ks:
            row[f"R@{kk}"] = _fmt(c.loc[f"recall@{kk}", "mean"], 3)
        rows.append(row)
    L += [_md_table(pd.DataFrame(rows)), ""]
    pm = res["model"]["pooled"]
    L += [
        f"Test rows {int(pm['n_rows']):,}, positives {int(pm['n_pos']):,} (rate {pm['positive_rate']:.4%}).",
        "",
    ]
    L += ["### Model minus baseline (paired)", ""]
    vr = []
    for b, v in out["vs_baselines"].items():
        d1, d2 = v["pr_auc_diff"], v[f"p@{k}_diff"]
        vr.append(
            {
                "vs": b,
                "PR-AUC diff [CI]": f"{d1['diff']:+.4f} [{d1['ci_low']:+.4f}, {d1['ci_high']:+.4f}]",
                f"P@{k} diff [CI]": f"{d2['diff']:+.3f} [{d2['ci_low']:+.3f}, {d2['ci_high']:+.3f}]",
                "model clearly better": "yes"
                if v["beats"] and d1["ci_low"] > 0 and d2["ci_low"] > 0
                else ("better, CI touches 0" if v["beats"] else "NO"),
            }
        )
    L += [_md_table(pd.DataFrame(vr)), ""]
    L += ["## Per year (mean over the year's test snapshots)", ""]
    for n in ("model", "B1"):
        by = res[n]["by_year"].reset_index()
        L += [
            f"**{n}**",
            "",
            _md_table(by[["year", "n_snapshots", "ap", *[f"precision@{kk}" for kk in ks]]]),
            "",
        ]
    L += [
        "![precision by year](figures/cv_precision_by_year.png)",
        "",
        "![PR curve](figures/cv_pr_curve.png)",
        "",
    ]

    L += [
        "## Ablations",
        "",
        f"Same folds, {m.ablation_n_configs} configs per fold (cheaper search). Deltas are against `abl_full_cheap` (all live features, same search).",
        "",
    ]
    ar = []
    for n, e in out["ablations"].items():
        s = e["summary"]
        row = {
            "variant": n,
            "complete": "yes" if e["complete"] else "NO",
            "PR-AUC": _fmt(s["pr_auc"], 4),
            f"P@{k}": _fmt(s[f"precision@{k}"], 3),
        }
        v = e.get("vs_full_cheap")
        row["PR-AUC delta [CI]"] = (
            f"{v['pr_auc_diff']['diff']:+.4f} [{v['pr_auc_diff']['ci_low']:+.4f}, {v['pr_auc_diff']['ci_high']:+.4f}]"
            if v
            else "-"
        )
        row[f"P@{k} delta [CI]"] = (
            f"{v[f'p@{k}_diff']['diff']:+.3f} [{v[f'p@{k}_diff']['ci_low']:+.3f}, {v[f'p@{k}_diff']['ci_high']:+.3f}]"
            if v
            else "-"
        )
        ar.append(row)
    L += [_md_table(pd.DataFrame(ar)), ""]
    L += [
        "Tier A = spine-only features (all eras); A+B adds the payload-detail features (NULL before 2023-06); A+B+C = `abl_full_cheap` adds enrichment (metadata, Hacker News).",
        "",
    ]
    if "monotone" in out:
        mo = out["monotone"]
        d1, d2 = mo["vs_full"]["pr_auc_diff"], mo["vs_full"][f"p@{k}_diff"]
        L += [
            "### Monotone constraints",
            "",
            f"`{', '.join(m.monotone_features)}` constrained non-decreasing, same search as `full`: PR-AUC {mo['summary']['pr_auc']:.4f} "
            f"(diff {d1['diff']:+.4f} [{d1['ci_low']:+.4f}, {d1['ci_high']:+.4f}]), P@{k} {mo['summary'][f'precision@{k}']:.3f} "
            f"(diff {d2['diff']:+.3f} [{d2['ci_low']:+.3f}, {d2['ci_high']:+.3f}]). "
            f"Decision: **{'keep the constraints' if mo['keep'] else 'no constraints'}** (kept only if neither metric is lower).",
            "",
        ]

    L += ["## Sanity checks", ""]
    s = out["sanity"]
    if "permuted_training" in s:
        v = s["permuted_training"]
        L += [
            f"- (a) Model trained on labels shuffled within each snapshot, evaluated on the true test labels: PR-AUC {v['pr_auc']:.4f} vs positive rate {v['positive_rate']:.4f} (limit {v['threshold']:.4f}): **{'PASS' if v['passed'] else 'FAIL'}**."
        ]
    v = s["permuted_test_labels"]
    L += [
        f"- (a') The final out-of-fold scores against test labels shuffled within each snapshot: PR-AUC {v['pr_auc']:.4f} vs rate {v['positive_rate']:.4f}: **{'PASS' if v['passed'] else 'FAIL'}**."
    ]
    if "stars7d_only" in s:
        v = s["stars7d_only"]
        L += [
            f"- (b) A model on `stars_7d` alone: PR-AUC {v['pr_auc']:.4f}, P@{k} {v[f'p@{k}']:.3f} vs B1 {v['b1_pr_auc']:.4f} / {v['b1_p']:.3f} (B1 breaks ties with the last day's stars; the single-feature model has coarse ties)."
        ]
    L += [""]

    L += ["## Calibration (pooled out-of-fold)", ""]
    c = out["calibration"]
    L += [
        _md_table(
            pd.DataFrame([{"": "raw score", **c["raw"]}, {"": "calibrated", **c["calibrated"]}]), 5
        ),
        "",
        f"The raw score comes from boosters fitted on {m.negative_sample:.0%} of the negatives, so it is not a probability; the calibrator (isotonic on the inner validation block, Platt below {m.min_positives_isotonic} positives) maps it to the real base rate. "
        f"Calibrators per fold: {dict(pd.Series([i['calibrator'] for i in infos]).value_counts())}.",
        "",
        "Reliability (10 equal-count bins):",
        "",
        _md_table(pd.DataFrame(c["reliability_calibrated"]), 5),
        "",
        "![reliability](figures/cv_reliability.png)",
        "",
    ]
    L += ["## Slices (pooled within the slice; rows ranked together)", ""]
    for n, tb in tables.items():
        L += [f"**{n}**", "", _md_table(tb) if len(tb) else "(no slice with enough positives)", ""]
    L += [
        "`era_post_2025_10` is 0 for every test row (the trusted era ends 2025-05-23), so there is nothing to split; the post-trim behaviour is untested by construction (ADR-009, ADR-022).",
        "",
    ]

    L += [f"## Lead time versus GitHub Trending (top-{k} flags)", ""]
    lr = []
    for n, r in res.items():
        lt = r["lead_time"]
        lr.append(
            {
                "": n,
                "trending repos": lt["n_trending_repos"],
                "never flagged": _fmt(lt["share_never_flagged"], 3),
                "flagged before Trending": _fmt(lt["share_flagged_before_trending"], 3),
                ">= 7 d before": _fmt(lt["share_flagged_7d_before"], 3),
                "median lead (d)": _fmt(lt["median_lead_days"], 1),
                "IQR (d)": f"{_fmt(lt['iqr_lead_days'][0], 1)} .. {_fmt(lt['iqr_lead_days'][1], 1)}",
            }
        )
    L += [_md_table(pd.DataFrame(lr)), ""]

    L += ["## Daily versus weekly scoring", ""]
    d = out.get("daily_check")
    if not d:
        L += ["Not run yet (`reports/metrics/daily_check.json` missing).", ""]
    else:
        L += [d.get("markdown", json.dumps(d)), ""]
    L += ["## Chosen hyperparameters per fold", ""]
    hp = pd.DataFrame(
        [
            {
                **{"fold": i["fold"]},
                **i["best_params"],
                "iter": i["best_iteration"],
                "val AP": i["val_ap"],
                "val pos": i["n_val_pos"],
            }
            for i in infos
        ]
    )
    L += [_md_table(hp), ""]
    return "\n".join(L)
