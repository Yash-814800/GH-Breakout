# gh-breakout model card: 20261019-b5ff585

## Intended use

Rank young, small, fast-starting GitHub repositories by the probability that they gain an unusual number of stars in the next 30 days (a *breakout*). It feeds a free public daily leaderboard. It is a research / discovery aid. A high rank is not an endorsement of a repository, its owners or its code, and it is not a quality or security assessment.

## Label and candidates

- Label `breakout_rel`: 30-day star gain in [D, D+30) >= max(100, the 0.995 quantile of the candidates' gain on the same snapshot D). About 0.5% of candidate rows are positive by construction.
- Candidates (the same SQL for training and daily scoring): age <= 90 days, < 200 stars before D, >= 5 stars in [D-14, D), no forks, mirrors or bot-owned repos.
- Snapshot D = the world as known at D 00:00 UTC; features use events strictly before D (leak test in `breakout build leak-test`).

## Training data

- Window of the shipped model: snapshots 2021-04-26 .. 2025-04-21 (weekly Mondays, matured labels only, 4 years). Last 3 months (after a 30-day embargo) stop the boosting and fit the calibrator.
- 68 features, all `live_available` (`config/feature_dictionary.yaml`, sha256 `49d9891cbff5`): Tier A spine-only star dynamics, activity, stargazer quality, tastemaker and owner features; Tier B payload detail (NULL before 2023-06-01); Tier C enrichment (primary language, owner type, Hacker News).
- LightGBM binary, 10% of the negatives subsampled for fitting; monotone constraints: off; chosen config {'num_leaves': 31, 'min_data_in_leaf': 200, 'feature_fraction': 0.8, 'learning_rate': 0.05, 'lambda_l2': 5.0, 'scale_pos_weight': 1.0}, 141 rounds.

## Evaluation design

Rolling-origin cross-validation (expanding window, 3-month test blocks, 30-day embargo between training and test, never a random split), all metrics out-of-fold, CIs from a block bootstrap over snapshot dates. The baseline B1 ranks by stars gained in the last 7 days. Details and the per-year tables: `reports/model_cv.md`.

### Cross-validated metrics (pooled over all test folds)

| | PR-AUC [95% CI] | ROC-AUC | P@25 [95% CI] |
|---|---|---|---|
| model | 0.1081 [0.1016, 0.1142] | 0.883 | 0.241 [0.228, 0.255] |
| B1 (7-day velocity) | 0.0286 [0.0246, 0.0345] | 0.816 | 0.109 [0.100, 0.118] |

### Holdout (2024-10-28 .. 2025-04-21, 26 snapshots, 285,198 rows, 1,444 positives)

Not used for fitting, early stopping or calibration of the evaluation model.

| | PR-AUC | P@25 |
|---|---|---|
| model | 0.1578 | 0.338 |
| B1 | 0.0323 | 0.106 |
| B2 | 0.0210 | 0.092 |
| B3 | 0.0256 | 0.102 |

Promotion decision: **promoted** (PR-AUC diff vs B1 +0.1255 [+0.1065, +0.1377], P@25 diff +0.232 [+0.183, +0.268]).

## Calibration

Isotonic regression (Platt scaling below 200 positives) fitted on the last 3 months of the training dates, which the booster did not train on. Holdout ECE raw 0.03660 vs calibrated 0.00088; Brier raw 0.01168 vs calibrated 0.00461. A probability is the share of such candidates that broke out within 30 days in the calibration period; the base rate is about 0.5%.

## Explanations

Every score comes with TreeSHAP contributions (log-odds); the leaderboard sentence names the top 3 positive and top 2 negative features using the phrases of the feature dictionary. Global importance: `reports/figures/shap_importance.png`, `reports/figures/shap_beeswarm.png`.

## Known limitations

- Attention outside GitHub is invisible except Hacker News stories linking to the repository; a repo that is about to trend on X, Reddit or YouTube is not seen until the stars arrive.
- Unstars are not observable; stars from the Events API only. Star farms and bots are not removed from the label (Phase 11 adds a detector); rapid fake-star growth can look like a breakout.
- GitHub trimmed Events payloads on 2025-10-07 (PR author, merged flag, commit lists). The shipped model uses only features that survive the trim; pre-2023-06 history has no payload detail (Tier B is NULL), so Tier B signals are learned from 2023-06 onward only.
- After 2025-05-23 GH Archive star capture collapsed (ADR-009). The training and evaluation data end there; live scoring on later data depends on the live source decision (ADR-010) and on metadata (language, owner type) that is 'Unknown' until fetched.
- Left-censoring: repository history before the first observed event is unknown; `age_days` is measured from the first observed activity.
- The label is relative (top 0.5% on each snapshot) with a floor of 100 stars; the base rate of true breakouts changes over time and between years.
- Weekly snapshots (Mondays) were used for training; daily scoring is checked for weekday effects in `reports/model_cv.md`.

## Ethical notes

Public repository names and the public GitHub usernames of stargazers are processed (aggregated into features; no per-user table is published). The leaderboard is not an endorsement. Owners who want a repository removed from the published leaderboard can open an issue in the project repository.
