"""Final model: holdout evaluation, packaging and promotion (Phase 8).

Two models are trained with the same recipe (``train.fit_calibrated``):

* the *evaluation model* on the training window that ends one embargo before the holdout block
  (the last ``model.holdout_months`` of matured snapshots); its predictions on the holdout feed
  the promotion rule and the reported holdout metrics;
* the *shipped model* on the most recent ``training.final_train_years`` of matured snapshots,
  except the last ``inner_validation_months`` (after an embargo), which stop the boosting and fit
  the calibrator. The booster is not refit on all data: the calibrator was fitted on predictions
  of exactly this booster, and a refit would make it describe a different model (ADR-025).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from breakout import features_dict
from breakout import paths as P
from breakout.config import Config
from breakout.logging import get_logger
from breakout.ml import baseline as B
from breakout.ml import calibrate as C
from breakout.ml import cv_report as R
from breakout.ml import dataset as D
from breakout.ml import explain as E
from breakout.ml import registry as G
from breakout.ml import train as T
from breakout.ml.splits import add_months

log = get_logger(__name__)


def git_state() -> dict[str, Any]:
    def run(*a: str) -> str:
        return subprocess.run(
            ["git", *a], capture_output=True, text=True, check=False
        ).stdout.strip()

    return {"sha": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def monotone_choice() -> bool:
    if R.METRICS_JSON.exists():
        return bool(json.loads(R.METRICS_JSON.read_text()).get("monotone", {}).get("keep", False))
    return False


def holdout_split(cfg: Config, dates: list) -> tuple[list, list]:
    """``(train_dates, holdout_dates)`` of the evaluation model."""
    latest = dates[-1]
    start = add_months(latest, -cfg.model.holdout_months)
    holdout = [d for d in dates if d > start]
    cutoff = holdout[0] - timedelta(days=cfg.training.embargo_days)
    lower = add_months(cutoff, -12 * cfg.training.final_train_years)
    return [d for d in dates if lower < d <= cutoff], holdout


def _frame(meta: pd.DataFrame, idx: np.ndarray, y: np.ndarray, score: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "repo_id": meta["repo_id"].to_numpy()[idx],
            "snapshot_date": meta["snapshot_date"].to_numpy()[idx],
            "score": score,
            "label": y[idx],
        }
    )


def train_final(
    cfg: Config,
    monotone: bool | None = None,
    candidate: bool = False,
) -> dict[str, Any]:
    ks = cfg.training.k_values
    k = 25 if 25 in ks else ks[0]
    monotone = monotone_choice() if monotone is None else monotone
    X, y_s, meta = D.load_training()
    y = y_s.to_numpy()
    snap = meta["snapshot_date"].to_numpy()
    dates = D.snapshot_dates(meta)
    latest = dates[-1]

    # --- evaluation model and holdout metrics
    tr_dates, ho_dates = holdout_split(cfg, dates)
    log.info(
        "evaluation model: train %s..%s, holdout %s..%s",
        tr_dates[0],
        tr_dates[-1],
        ho_dates[0],
        ho_dates[-1],
    )
    ev = T.fit_calibrated(
        cfg, X, y, snap, tr_dates, n_configs=cfg.model.search_n_configs, monotone=monotone
    )
    ho_idx = np.flatnonzero(np.isin(snap, np.array(ho_dates, dtype="datetime64[ns]")))
    p_raw = T.predict(ev.booster, X.iloc[ho_idx], ev.categories)
    cand = _frame(meta, ho_idx, y, p_raw)
    cand["prob"] = ev.calibrator.predict(p_raw)
    base, _ = R.baseline_inputs()
    base_x = base.iloc[ho_idx]
    b = {n: _frame(meta, ho_idx, y, fn(base_x).to_numpy()) for n, fn in B.BASELINES.items()}
    holdout = {
        "dates": [str(ho_dates[0]), str(ho_dates[-1])],
        "n_snapshots": len(ho_dates),
        "n_rows": int(len(ho_idx)),
        "n_pos": int(y[ho_idx].sum()),
        "model": R.summarize(cand, ks),
        **{n: R.summarize(f, ks) for n, f in b.items()},
        "calibration": {
            "raw": C.calibration_summary(y[ho_idx], p_raw),
            "calibrated": C.calibration_summary(y[ho_idx], cand["prob"].to_numpy()),
        },
        "eval_model": {
            "best_params": ev.result.params,
            "best_iteration": ev.result.best_iteration,
            **ev.stats,
        },
    }
    n_boot = cfg.model.n_boot

    # --- champion on the same rows (if any)
    reg = G.load_registry()
    champ_frame = None
    if reg["champion"] and (G.models_dir() / reg["champion"] / "model.txt").exists():
        champ = G.load_model(G.models_dir() / reg["champion"])
        xc = D.apply_categories(X.iloc[ho_idx][champ.features], champ.categories)
        champ_frame = _frame(meta, ho_idx, y, np.asarray(champ.booster.predict(xc), dtype=float))
    decision = G.decide(
        cand[["repo_id", "snapshot_date", "score", "label"]], b["B1"], champ_frame, ks, n_boot, k
    )
    decision["holdout_vs"] = {
        n: R.promotion_rule(cand[["repo_id", "snapshot_date", "score", "label"]], f, ks, n_boot, k)
        for n, f in b.items()
    }

    # --- shipped model
    lower = add_months(latest, -12 * cfg.training.final_train_years)
    prod_dates = [d for d in dates if d > lower]
    log.info("shipped model: train %s..%s", prod_dates[0], prod_dates[-1])
    fm = T.fit_calibrated(
        cfg, X, y, snap, prod_dates, n_configs=cfg.model.search_n_configs, monotone=monotone
    )
    reference = E.reference_medians(
        X.iloc[np.flatnonzero(np.isin(snap, np.array(prod_dates, dtype="datetime64[ns]")))]
    )

    git = git_state()
    version = G.new_version(git["sha"])
    cv_summary = json.loads(R.METRICS_JSON.read_text()) if R.METRICS_JSON.exists() else None
    metrics = {
        "version": version,
        "git": git,
        "monotone": monotone,
        "features": fm.features,
        "dictionary_sha256": features_dict.dictionary_hash(),
        "training_window": [str(prod_dates[0]), str(prod_dates[-1])],
        "shipped": {
            "best_params": fm.result.params,
            "best_iteration": fm.result.best_iteration,
            "val_ap": fm.result.val_ap,
            **fm.stats,
        },
        "holdout": holdout,
        "cv": (cv_summary or {}).get("main"),
        "cv_vs_baselines": (cv_summary or {}).get("vs_baselines"),
        "decision": decision,
    }
    from breakout.ml import card

    out = G.save_package(
        G.models_dir() / version,
        fm.booster,
        fm.calibrator,
        fm.categories,
        fm.features,
        reference,
        B._jsonable(metrics),
        card.render(cfg, metrics, cv_summary),
    )
    ev_reference = E.reference_medians(
        X.iloc[np.flatnonzero(np.isin(snap, np.array(tr_dates, dtype="datetime64[ns]")))]
    )
    G.save_core(
        out / "eval_model", ev.booster, ev.calibrator, ev.categories, ev.features, ev_reference
    )
    holdout_path = out / "holdout_predictions.parquet"
    cand.to_parquet(holdout_path, index=False)
    if candidate:
        decision_reg = dict(decision)
        decision_reg["promote"] = False
        decision_reg["is_candidate"] = True
    else:
        decision_reg = decision
    reg = G.register(
        reg,
        version,
        {
            "holdout": holdout,
            "cv_pooled": (cv_summary or {}).get("main", {}).get("model", {}).get("pooled"),
        },
        decision_reg,
    )
    G.save_registry(B._jsonable(reg))
    log.info(
        "version %s, promoted=%s, champion=%s, candidate=%s",
        version,
        decision_reg["promote"],
        reg["champion"],
        candidate,
    )
    return {
        "version": version,
        "promoted": decision_reg["promote"],
        "champion": reg["champion"],
        "candidate": candidate,
        "path": str(out),
    }


def promote_candidate(
    cfg: Config,
    version: str | None = None,
    if_better: bool = True,
) -> dict[str, Any]:
    """Evaluate candidate model and promote to champion if it beats current champion and B1."""
    reg = G.load_registry()
    if not reg.get("versions"):
        raise LookupError("No versions in registry")

    target_v = version or reg["versions"][-1]["version"]
    v_entry = next((v for v in reg["versions"] if v["version"] == target_v), None)
    if not v_entry:
        raise LookupError(f"Version {target_v} not found in registry")

    current_champ = reg.get("champion")
    decision = v_entry.get("decision", {})
    metrics = v_entry.get("metrics", {})

    can_promote = False
    if if_better:
        vs_b1 = decision.get("vs_B1", {})
        beats_b1 = vs_b1.get("beats", False)
        vs_champ = decision.get("vs_champion", {})
        beats_champ = vs_champ.get("beats", True) if current_champ else True
        can_promote = bool(beats_b1 and beats_champ)
    else:
        can_promote = True

    retrain_dir = P.ROOT / "reports" / "retrain"
    retrain_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now(UTC).date().isoformat()
    report_path = retrain_dir / f"{today_str}.md"

    if can_promote:
        reg["champion"] = target_v
        v_entry["decision"]["promote"] = True
        G.save_registry(B._jsonable(reg))
        log.info("Promoted candidate %s to champion", target_v)
        res_status = f"Promoted {target_v} to champion (beats B1 and champion)"
    else:
        log.info("Candidate %s rejected; retaining champion %s", target_v, current_champ)
        res_status = (
            f"Retained champion {current_champ}; candidate {target_v} did not beat threshold"
        )

    report_content = f"""# Retraining and Promotion Report ({today_str})

**Date:** {today_str}
**Candidate Version:** `{target_v}`
**Previous Champion:** `{current_champ}`
**Status:** {res_status}

## Decision
```json
{json.dumps(decision, indent=2)}
```

## Metrics
```json
{json.dumps(metrics.get("holdout", {}), indent=2)}
```
"""
    report_path.write_text(report_content)
    log.info("Wrote retrain report to %s", report_path)

    return {
        "candidate": target_v,
        "promoted": can_promote,
        "champion": reg["champion"],
        "report_path": str(report_path),
    }


def explain_figures(cfg: Config, version: str, n: int = 20000) -> dict[str, Any]:
    """Global SHAP importance + beeswarm of a packaged model on a sample of its training rows."""
    model = G.load_model(G.models_dir() / version)
    X, _, meta = D.load_training(features=model.features)
    keep = np.flatnonzero(
        (
            meta["snapshot_date"]
            >= meta["snapshot_date"].max() - pd.DateOffset(years=cfg.training.final_train_years)
        ).to_numpy()
    )
    Xs = X.iloc[keep].sample(n=min(n, len(keep)), random_state=cfg.model.seed)
    return E.global_figures(model.booster, D.apply_categories(Xs, model.categories), n=n)


def repo_names(cfg: Config, ids: list[int]) -> dict[int, str]:
    """Display names (the most recent seen name per repo_id); empty when the history is absent."""
    import duckdb

    from breakout.enrich import names

    path = names.history_path(cfg)
    if not path.exists() or not ids:
        return {}
    con = duckdb.connect()
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=1")
    try:
        idl = ", ".join(str(int(i)) for i in ids)
        rows = con.execute(
            f"""SELECT repo_id, repo_name FROM (
                  SELECT repo_id, repo_name, row_number() OVER (
                    PARTITION BY repo_id ORDER BY last_seen DESC, first_seen DESC) rn
                  FROM read_parquet('{path}') WHERE repo_id IN ({idl})) WHERE rn = 1"""
        ).fetchall()
    finally:
        con.close()
    return {int(r[0]): str(r[1]) for r in rows}


def predict_date(
    cfg: Config, d: str, top: int = 10, features_file: str | None = None
) -> pd.DataFrame:
    """Score the live features file of ``d`` with the champion; returns the top rows."""
    from pathlib import Path

    from breakout.features.build import LIVE_DIR

    path = Path(features_file) if features_file else LIVE_DIR / f"features_{d}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `breakout build features --date {d}` first")
    model = G.load_champion()
    df = pd.read_parquet(path)
    pred = G.predict(model, df)
    out = pd.concat([df[["repo_id"]], pred], axis=1).sort_values(
        ["raw_score", "repo_id"], ascending=[False, True]
    )
    out = out.head(top).copy()
    names = repo_names(cfg, [int(i) for i in out["repo_id"]])
    out.insert(1, "repo", [names.get(int(i), f"repo_id={int(i)}") for i in out["repo_id"]])
    out["model_version"] = model.version
    return out.reset_index(drop=True)
