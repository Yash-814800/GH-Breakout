# Phase 06 — Candidate universe, labels, baseline, evaluation harness

## Goal
Before any ML: define exactly **who is scored** (candidates), **what counts as success**
(labels), build the **evaluation harness** (rolling-origin splits with embargo, metrics, lead
time vs GitHub Trending), and measure a **simple baseline**. Every later model must beat this.

## Prerequisites
Phase 05 done (`int_repo_birth`, `int_repo_star_daily`, `int_young_moving_repos`, enrichment staged).

## Deliverables

### 6.1 Snapshot dates — `models/marts/mart_snapshot_dates.sql`
- `snapshot_dates_mode = 'weekly_history'`: every `training.snapshot_weekday` (Monday) from
  `training.first_snapshot` up to the last date ≤ (latest fully ingested day + 1). Columns
  `snapshot_date, is_label_matured` (`snapshot_date + horizon_days <= latest_ingested_day + 1`).
- `snapshot_dates_mode = 'single'`: exactly `var('snapshot_date')`.
- "Latest fully ingested day" comes from a small macro reading `max(created_at)` of `stg_stars`
  within the window, truncated to the last complete UTC day; document it.

### 6.2 Candidates — `models/marts/mart_candidates.sql`
Grain `(repo_id, snapshot_date)`. A repo is a candidate on `D` iff **all** hold (values from vars,
which come from `config/project.yaml`):
- `birth_at < D` and `age_days = date_diff('day', birth_at, D) <= max_age_days`
- `stars_total_before_D < max_stars_total` (sum of `n_stars` over days `< D`)
- `stars_14d >= min_stars_14d` (days in `[D-14, D)`)
- not `is_fork`, not `is_mirror_like`, owner not a bot (owner login from the name valid on D-1
  matches `stg_bot_actors`/pattern), not left-censored (see Phase 5 birth caveat)
Columns: `repo_id, snapshot_date, age_days, stars_total_before, stars_1d, stars_7d, stars_14d,
stars_prev_7d (days [D-14, D-7)), birth_source, repo_name_at_D` (display only).
Implement with a date spine join restricted to `int_young_moving_repos` and window sums over
`int_repo_star_daily` (use `SUM(n_stars) FILTER (WHERE day >= D - 14 AND day < D)` patterns or a
cumulative-sum + ASOF approach; choose the faster and note it).
**This exact model is used for live scoring** (mode `single`). No Python re-implementation.

Tests: unique grain; `stars_14d >= min`; `age_days between 0 and max`; `stars_total_before < max`;
no forks. Add a singular test that a hand-picked known repo appears as a candidate on an expected date
(pick one from the data and hard-code it with a comment).

### 6.3 Labels — `models/marts/mart_labels.sql`
Grain `(repo_id, snapshot_date)` for candidates on **matured** snapshot dates:
- `gain_30d` = stars in `[D, D + horizon_days)`
- `threshold_rel(D) = GREATEST(relative_floor_gain, quantile_cont(gain_30d, relative_quantile) over all candidates on D)`
- `breakout_rel = gain_30d >= threshold_rel(D)` (primary; ≈ top 0.5%)
- `breakout_abs = gain_30d >= absolute_min_gain` (secondary)
- `days_to_threshold`: first day offset in `[0, horizon)` when cumulative forward stars ≥ threshold (NULL if never)
- `first_trending_date`: first date in `[D, D + 60)` the repo appears in `stg_trending` (NULL if never or
  if trending coverage is missing that period; add `trending_covered` boolean)
Tests: label only on matured dates; positive rate per snapshot between 0.2% and 2% (warn severity);
`gain_30d >= 0`.

### 6.4 Export for Python
- CLI `breakout build labels` runs `mart_snapshot_dates mart_candidates mart_labels` for history and
  exports `data/derived/labels/candidates_labels.parquet` (join of both) + uploads to the derived HF repo
  (`labels/`).
- Print and record in PROGRESS: snapshots count, median candidates per snapshot, positive rate per year,
  number of distinct positive repos.

### 6.5 Rolling-origin splits — `src/breakout/ml/splits.py`
- `make_folds(snapshot_dates, *, test_window_months, embargo_days, min_train_years, mode="expanding",
  sliding_years=None) -> list[Fold]` where `Fold(train_dates, test_dates, test_start, test_end)`.
- Rules: test windows are consecutive, non-overlapping blocks of `test_window_months`; first test block
  starts after `min_train_years` of snapshots; `train_dates = {d : d <= test_start - embargo_days}`;
  only matured dates anywhere. Assert `embargo_days >= horizon_days` at runtime.
- Unit tests: no train date within embargo of test start; no overlap; matured-only; sliding mode window length.

### 6.6 Metrics — `src/breakout/ml/metrics.py`
Input: DataFrame `(repo_id, snapshot_date, score, label[, prob])`.
- Per snapshot: `precision@k`, `recall@k` for `k in training.k_values`, average precision.
- Pooled: PR-AUC (average precision over all rows), ROC-AUC, positive rate.
- If `prob` present: Brier score, log loss, expected calibration error (10 quantile bins).
- Aggregations: mean over snapshots (primary for @k), by calendar year, and a **block bootstrap over
  snapshot dates** (1,000 resamples) for 95% CIs.
- **Lead time vs Trending** (`lead_time_report(preds, labels, flag_rule)`): among rows where
  `trending_covered` and the repo appeared on Trending within 60 days, define the repo's **first flag
  date** = earliest snapshot it was in the top-k (default k=25) of its snapshot; lead time =
  `first_trending_date - first_flag_date` in days (positive = we were earlier). Report median, IQR, share
  flagged before Trending, share never flagged. State the snapshot resolution (weekly in backtests).
- Unit tests with tiny hand-computed examples for every metric.

### 6.7 Baselines — `src/breakout/ml/baseline.py`
- `B1`: score = `stars_7d` (ties broken by `stars_1d`).
- `B2`: score = `stars_7d / (stars_total_before + 10)` (relative velocity).
- `B3`: score = `stars_7d - stars_prev_7d` (acceleration).
- For each fold's test dates, score candidates and compute metrics. Also produce a "probability" for B1
  via isotonic calibration fit on the fold's training dates (so calibration metrics are comparable later).
- CLI `breakout ml baseline` → `reports/baseline.md` (+ `reports/metrics/baseline.json`) with: fold table,
  per-year table, pooled metrics with CIs, lead-time summary, and figures in `reports/figures/`
  (PR curve, precision@25 by year). Use matplotlib, small PNGs.

## Rules / gotchas
- Candidate and label logic lives **only** in dbt SQL; Python reads the exported table.
- Never compute the relative threshold using only train or only test rows — it is a per-snapshot
  property of the label definition and is computed over all candidates on that snapshot.
- Positives are rare and the same repo appears on several consecutive snapshots; that is expected.
  Metrics are computed per snapshot, then averaged, which handles it.

## Acceptance criteria
- [ ] `mart_candidates` / `mart_labels` built for history; dbt tests pass.
- [ ] `reports/baseline.md` exists with per-year metrics, CIs, and lead time; numbers copied into PROGRESS.
- [ ] Split and metric unit tests pass.
- [ ] Sanity check in report: list the top 10 B1-ranked candidates on 3 historical dates with their
      realized `gain_30d` and label.
