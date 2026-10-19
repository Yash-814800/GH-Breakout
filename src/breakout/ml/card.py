"""Model card text (``docs/model_card.md`` and the card of every packaged version)."""

from __future__ import annotations

from typing import Any

from breakout.config import Config


def _f(x: Any, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render(cfg: Config, metrics: dict[str, Any], cv: dict[str, Any] | None) -> str:
    ho = metrics["holdout"]
    ks = cfg.training.k_values
    k = 25 if 25 in ks else ks[0]
    dec = metrics["decision"]
    L = [
        f"# gh-breakout model card: {metrics['version']}",
        "",
        "## Intended use",
        "",
        "Rank young, small, fast-starting GitHub repositories by the probability that they gain an unusual number of stars in the next 30 days "
        "(a *breakout*). It feeds a free public daily leaderboard. It is a research / discovery aid. A high rank is not an endorsement of a "
        "repository, its owners or its code, and it is not a quality or security assessment.",
        "",
        "## Label and candidates",
        "",
        f"- Label `breakout_rel`: 30-day star gain in [D, D+{cfg.labels.horizon_days}) >= max({cfg.labels.relative_floor_gain}, the {cfg.labels.relative_quantile} quantile of the candidates' gain on the same snapshot D). About 0.5% of candidate rows are positive by construction.",
        f"- Candidates (the same SQL for training and daily scoring): age <= {cfg.candidates.max_age_days} days, < {cfg.candidates.max_stars_total} stars before D, >= {cfg.candidates.min_stars_14d} stars in [D-14, D), no forks, mirrors or bot-owned repos.",
        "- Snapshot D = the world as known at D 00:00 UTC; features use events strictly before D (leak test in `breakout build leak-test`).",
        "",
        "## Training data",
        "",
        f"- Window of the shipped model: snapshots {metrics['training_window'][0]} .. {metrics['training_window'][1]} (weekly Mondays, matured labels only, {cfg.training.final_train_years} years). "
        f"Last {cfg.model.inner_validation_months} months (after a {cfg.training.embargo_days}-day embargo) stop the boosting and fit the calibrator.",
        f"- {len(metrics['features'])} features, all `live_available` (`config/feature_dictionary.yaml`, sha256 `{metrics['dictionary_sha256'][:12]}`): Tier A spine-only star dynamics, activity, stargazer quality, tastemaker and owner features; "
        "Tier B payload detail (NULL before 2023-06-01); Tier C enrichment (primary language, owner type, Hacker News).",
        f"- LightGBM binary, {cfg.model.negative_sample:.0%} of the negatives subsampled for fitting; monotone constraints: {'on' if metrics['monotone'] else 'off'}; "
        f"chosen config {metrics['shipped']['best_params']}, {metrics['shipped']['best_iteration']} rounds.",
        "",
        "## Evaluation design",
        "",
        f"Rolling-origin cross-validation (expanding window, {cfg.training.test_window_months}-month test blocks, {cfg.training.embargo_days}-day embargo between training and test, never a random split), "
        "all metrics out-of-fold, CIs from a block bootstrap over snapshot dates. The baseline B1 ranks by stars gained in the last 7 days. "
        "Details and the per-year tables: `reports/model_cv.md`.",
        "",
    ]
    if cv:
        m, b1 = cv["main"]["model"], cv["main"]["B1"]
        kk = f"precision@{k}"
        L += [
            "### Cross-validated metrics (pooled over all test folds)",
            "",
            f"| | PR-AUC [95% CI] | ROC-AUC | P@{k} [95% CI] |",
            "|---|---|---|---|",
        ]
        for name, r in (("model", m), ("B1 (7-day velocity)", b1)):
            ci = r["pooled_pr_auc_ci"]
            pk = r["ci"]
            pk = [x for x in pk if x.get("index") == kk or x.get("level_0") == kk]
            L.append(
                f"| {name} | {r['pooled']['pr_auc']:.4f} [{ci['ci_low']:.4f}, {ci['ci_high']:.4f}] | {r['pooled']['roc_auc']:.3f} | "
                + (
                    f"{pk[0]['mean']:.3f} [{pk[0]['ci_low']:.3f}, {pk[0]['ci_high']:.3f}]"
                    if pk
                    else "see report"
                )
                + " |"
            )
        L.append("")
    L += [
        f"### Holdout ({ho['dates'][0]} .. {ho['dates'][1]}, {ho['n_snapshots']} snapshots, {ho['n_rows']:,} rows, {ho['n_pos']:,} positives)",
        "",
        "Not used for fitting, early stopping or calibration of the evaluation model.",
        "",
        f"| | PR-AUC | P@{k} |",
        "|---|---|---|",
        f"| model | {_f(ho['model']['pr_auc'], 4)} | {_f(ho['model'][f'precision@{k}'])} |",
        f"| B1 | {_f(ho['B1']['pr_auc'], 4)} | {_f(ho['B1'][f'precision@{k}'])} |",
        f"| B2 | {_f(ho['B2']['pr_auc'], 4)} | {_f(ho['B2'][f'precision@{k}'])} |",
        f"| B3 | {_f(ho['B3']['pr_auc'], 4)} | {_f(ho['B3'][f'precision@{k}'])} |",
        "",
        f"Promotion decision: **{'promoted' if dec['promote'] else 'NOT promoted'}** "
        f"(PR-AUC diff vs B1 {dec['vs_B1']['pr_auc_diff']['diff']:+.4f} [{dec['vs_B1']['pr_auc_diff']['ci_low']:+.4f}, {dec['vs_B1']['pr_auc_diff']['ci_high']:+.4f}], "
        f"P@{k} diff {dec['vs_B1'][f'p@{k}_diff']['diff']:+.3f} [{dec['vs_B1'][f'p@{k}_diff']['ci_low']:+.3f}, {dec['vs_B1'][f'p@{k}_diff']['ci_high']:+.3f}]).",
        "",
        "## Calibration",
        "",
        "Isotonic regression (Platt scaling below 200 positives) fitted on the last 3 months of the training dates, which the booster did not train on. "
        f"Holdout ECE raw {_f(ho['calibration']['raw']['ece'], 5)} vs calibrated {_f(ho['calibration']['calibrated']['ece'], 5)}; "
        f"Brier raw {_f(ho['calibration']['raw']['brier'], 5)} vs calibrated {_f(ho['calibration']['calibrated']['brier'], 5)}. "
        "A probability is the share of such candidates that broke out within 30 days in the calibration period; the base rate is about 0.5%.",
        "",
        "## Explanations",
        "",
        "Every score comes with TreeSHAP contributions (log-odds); the leaderboard sentence names the top 3 positive and top 2 negative features "
        "using the phrases of the feature dictionary. Global importance: `reports/figures/shap_importance.png`, `reports/figures/shap_beeswarm.png`.",
        "",
        "## Known limitations",
        "",
        "- Attention outside GitHub is invisible except Hacker News stories linking to the repository; a repo that is about to trend on X, Reddit or YouTube is not seen until the stars arrive.",
        "- Unstars are not observable; stars from the Events API only. Star farms and bots are not removed from the label (Phase 11 adds a detector); rapid fake-star growth can look like a breakout.",
        "- GitHub trimmed Events payloads on 2025-10-07 (PR author, merged flag, commit lists). The shipped model uses only features that survive the trim; pre-2023-06 history has no payload detail (Tier B is NULL), so Tier B signals are learned from 2023-06 onward only.",
        "- After 2025-05-23 GH Archive star capture collapsed (ADR-009). The training and evaluation data end there; live scoring on later data depends on the live source decision (ADR-010) and on metadata (language, owner type) that is 'Unknown' until fetched.",
        "- Left-censoring: repository history before the first observed event is unknown; `age_days` is measured from the first observed activity.",
        "- The label is relative (top 0.5% on each snapshot) with a floor of 100 stars; the base rate of true breakouts changes over time and between years.",
        "- Weekly snapshots (Mondays) were used for training; daily scoring is checked for weekday effects in `reports/model_cv.md`.",
        "",
        "## Ethical notes",
        "",
        "Public repository names and the public GitHub usernames of stargazers are processed (aggregated into features; no per-user table is published). "
        "The leaderboard is not an endorsement. Owners who want a repository removed from the published leaderboard can open an issue in the project repository.",
        "",
    ]
    return "\n".join(L)
