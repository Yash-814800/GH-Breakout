# Phase 08 — LightGBM model, rolling-origin CV, calibration, SHAP, model card, registry

## Goal
Train a LightGBM classifier for `breakout_rel`, evaluate it honestly with the Phase 6 harness
against the baselines, calibrate it so leaderboard probabilities mean what they say, explain every
prediction in plain English with SHAP, and publish a versioned model with a model card.

## Prerequisites
Phase 07 done (training table on disk/HF, feature dictionary, leak test passing).

## Deliverables
1. Add deps: `lightgbm`, `shap`, `scikit-learn` (if not already), `pandas`, `numpy`, `matplotlib`.
   Load training data with DuckDB → Arrow → pandas only for the columns needed; cast floats to float32.
2. `src/breakout/ml/dataset.py`
   - `load_training(years=None) -> (X, y, meta)`; meta = `repo_id, snapshot_date, gain_30d, first_trending_date, trending_covered`.
   - Feature list = dictionary entries with `allowed: true`. Categorical columns (`primary_language`,
     `owner_type`) as pandas `category` with **categories fixed from the training fold** (unseen → 'Other').
     Persist category mappings with the model.
   - Drop rows with unmatured labels (assert none exist).
3. `src/breakout/ml/train.py`
   - LightGBM binary objective, `metric=average_precision`, early stopping on an inner **time-based**
     validation split (the last 3 months of the fold's training dates, with its own embargo of
     `horizon_days` before it). Never random validation.
   - Small, explicit hyperparameter search (e.g. 12–20 configs over `num_leaves ∈ {15,31,63}`,
     `min_data_in_leaf ∈ {50,200,500}`, `feature_fraction ∈ {0.6,0.8}`, `learning_rate ∈ {0.03,0.05}`,
     `lambda_l2 ∈ {0,5}`), selected on the inner validation average precision. Fixed seed. Do not tune on
     test folds.
   - Class imbalance: try `scale_pos_weight` vs none in the search; calibration fixes probabilities later.
   - Optional monotone constraints (`stars_7d`, `sg_share_experienced` non-decreasing) as a config flag —
     evaluate both and keep only if not worse.
4. `src/breakout/ml/cv.py` + CLI `breakout ml cv`
   - For each fold from `splits.make_folds` (expanding mode): train, predict test, collect out-of-fold (OOF)
     predictions with fold id. Save `data/derived/ml/oof_predictions.parquet`
     (`repo_id, snapshot_date, fold, raw_score, prob_calibrated, label, gain_30d`) and upload to derived HF repo.
   - Compute metrics with `ml/metrics.py` for model and all baselines **on the same rows**.
   - Ablations (one CV run each, cheaper settings allowed): Tier A only; A+B; A+B+C; without tastemaker;
     without stargazer-quality group. Report the delta in PR-AUC and precision@25.
   - **Sanity checks**: (a) label-permutation within snapshot → PR-AUC ≈ positive rate, (b) a model using only
     `stars_7d` ≈ baseline B1. Fail loudly if (a) is not near random.
   - Performance by year, by `era_post_2025_10`, by language (top 10), by `detail_coverage_28d` bucket.
5. `src/breakout/ml/calibrate.py`
   - Per fold: fit isotonic regression (fallback Platt if < 200 positives) on the fold's inner validation
     predictions (data the booster did not train on); apply to that fold's test predictions → `prob_calibrated`.
   - For the final model: calibrator fit on the most recent held-out block (see 7).
   - Reliability diagram (10 quantile bins with counts) + ECE and Brier, before vs after calibration.
6. `src/breakout/ml/explain.py`
   - SHAP TreeExplainer on the raw booster (log-odds space). For any scored row: top 3 positive and top 2
     negative contributions.
   - `explain_sentence(row, contributions) -> str` using `feature_dictionary.yaml` templates. Value formatting:
     shares → percent, hours → "~5 h", counts → integers. Join as one sentence, e.g.
     "Flagged because 72% of recent stars come from experienced accounts, issues get a first response in ~3 h,
     and 3 new contributors joined in the last 4 weeks." Unit-test the formatter with fixtures.
   - Global importance: mean |SHAP| bar chart and a beeswarm on a 20k-row sample → `reports/figures/`.
7. `src/breakout/ml/final.py` + CLI `breakout ml train-final`
   - Train on the most recent `training.final_train_years` of matured snapshots **except** the last 3 months,
     which (after a `horizon_days` embargo) are used for early stopping and calibration. Then optionally refit
     the booster on all data with the chosen number of iterations (record the choice).
   - Package `models/<version>/`: `model.txt` (LightGBM native), `calibrator.pkl` (or JSON breakpoints —
     prefer JSON: isotonic `X_thresholds_`/`y_thresholds_` so no pickle is needed), `categories.json`,
     `features.json` (ordered list + dictionary hash), `metrics.json` (CV summary + holdout), `card.md`.
     Version = `YYYYMMDD-<short git sha>`.
8. `src/breakout/ml/registry.py`
   - `registry.json` in the models HF repo: list of versions with metrics and `champion` pointer.
   - `promote(candidate)` rule: promote only if on the shared most recent holdout block the candidate beats the
     current champion **and** baseline B1 on PR-AUC and mean precision@25 (CI of the difference vs champion must
     not be clearly negative). First model: must beat B1. Record the decision with numbers in registry.json.
   - `load_champion()` downloads (cached) and returns `(booster, calibrator, categories, features)`;
     `predict(df) -> DataFrame(raw_score, prob, top_contribs)` used by Phase 9.
9. `docs/model_card.md` (also uploaded as the model repo README): intended use, label definition, candidate
   universe, training data window, features by tier, evaluation design (rolling-origin, embargo), metrics with CIs
   (pooled and by year), baselines, calibration plot, lead time vs Trending, ablations, known limitations
   (no off-GitHub attention except HN, unstars invisible, payload trimming, bots/fake stars, left-censoring),
   ethical notes (public usernames are processed; leaderboard is not an endorsement).
10. `reports/model_cv.md`: fold table, per-year table, ablations, sanity checks, calibration, lead time.
11. Daily-vs-weekly check: score **daily** snapshots (mode `single`) for the last 4 weeks of the holdout with
    the final model and confirm calibration and precision@k do not differ meaningfully by weekday (training
    used Mondays). Report in `reports/model_cv.md`.

## Rules / gotchas
- Never compute metrics on training rows. Never fit calibration on training rows of the booster.
- Never pass `repo_id`, `snapshot_date`, names, or label-derived columns as features (assert in code).
- Keep LightGBM `deterministic=true`, `seed` fixed, `num_threads` from config.
- Training must fit in 16 GB RAM (the weekly retrain runs on a GitHub runner). If the training table is too
  large, subsample negatives within each snapshot (keep all positives) by a recorded factor and correct the
  calibrator accordingly (calibrate on unsampled validation data).

## Acceptance criteria
- [ ] `reports/model_cv.md` shows the model vs B1/B2/B3 with CIs, per year; ablations; sanity checks passed.
- [ ] If the model does **not** beat B1, say so plainly, keep B1 as champion, and propose next steps — do not
      massage the evaluation.
- [ ] Final model published to the HF models repo; `registry.json` has a champion; model card rendered.
- [ ] `breakout ml predict --date <yesterday>` (uses live features file) prints top 10 with calibrated
      probabilities and explanation sentences.
