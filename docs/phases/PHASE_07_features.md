# Phase 07 — Point-in-time feature marts (Tier A / B / C), tastemaker score

## Goal
Build `mart_repo_features`: one row per `(repo_id, snapshot_date)` candidate, using **only data
available before `snapshot_date`**, computed by the same SQL for history (weekly snapshots) and for
live scoring (single date). Prove there is no leakage with an automated time-travel test.

## Prerequisites
Phase 06 done (`mart_candidates`, `mart_labels`, baseline report).

## Design rules (enforced in review and tests)
- Every feature CTE joins to `mart_candidates` and filters source rows with `< snapshot_date`
  (timestamps) or `< snapshot_date` (days). Never `<=`. Window `[D - n, D)`.
- Features depending on outcomes (tastemaker, owner prior breakouts, HN points) use only outcomes
  **known before D** (see each definition).
- Tier B features are NULL when the window has no detail coverage. Never fill with 0 —
  LightGBM handles NaN. Provide `detail_coverage_28d` so the model knows.
- **No calendar features** (day-of-week, month): training snapshots are all Mondays while live scoring
  runs daily; calendar features would not transfer.
- Organize as feature-group models `feat_<group>` (grain `(repo_id, snapshot_date)`), then
  `mart_repo_features` = `mart_candidates` LEFT JOIN all groups. Heavy groups may be `external`
  materializations partitioned by `year(snapshot_date)`.
- Every feature is registered in `config/feature_dictionary.yaml` (see 7.3). A unit test fails if
  `mart_repo_features` has a column missing from the dictionary or vice versa.

## 7.1 Feature groups and definitions

### `feat_star_dynamics` (Tier A)
`stars_1d, stars_3d, stars_7d, stars_14d, stars_28d, stars_total_before, star_accel_7d = stars_7d - stars_prev_7d,
star_ratio_7d = (stars_7d + 1) / (stars_prev_7d + 1), days_since_first_star, age_days,
star_active_days_14d` (days with ≥1 star), `star_gini_14d` (Gini coefficient of the 14 daily counts,
zeros included), `star_max_day_share_14d` (max daily / stars_14d), `star_max_hour_share_7d` (max stars in
any single UTC hour / stars_7d, from `stg_stars` timestamps).
Burstiness separates one-day spikes (e.g. a single link share) from sustained growth.

### `feat_activity` (Tier A, from `int_repo_daily_activity`, `int_contributor_*`)
`forks_7d, forks_14d, fork_star_ratio_14d = forks_14d / (stars_14d + 1), distinct_actors_14d,
issue_events_14d, issue_comments_14d, pr_events_14d, reviews_14d, releases_total_before,
days_since_last_release` (NULL if none), `push_active_days_14d, distinct_pushers_28d,
event_type_entropy_14d` (Shannon entropy over counts by event type),
`distinct_contributors_28d` (actors with issue/PR/comment/review in window),
`new_contributors_28d` (their first contribution to this repo is in the window, from `int_contributor_first_seen`),
`first_time_contributor_rate_28d = new / NULLIF(distinct, 0)`, `top_actor_share_28d`
(share of non-star events by the single most active actor), `sessions_28d, median_session_minutes_28d,
distinct_session_actors_28d` (from `int_contributor_sessions`, sessions that started in window).

### `feat_stargazers` (Tier A + actor-age enrichment; from `int_star_events_enriched`)
Over first stars in `[D-14, D)`:
`sg_n, sg_share_experienced` (actor_events_prior_90d ≥ 10 AND actor_repos_prior_90d ≥ 2),
`sg_median_account_age_days, sg_share_account_lt_30d, sg_share_zero_prior_activity,
sg_median_stars_same_day, sg_share_bulk_starrers` (actor_stars_same_day ≥ 50).
Retention-so-far (from `int_stargazer_later_actions`): of stargazers who starred in `[D-28, D-7)`,
share who forked / opened an issue / opened a PR / commented on the repo **before D**:
`sg_retention_any_28d, sg_retention_fork_28d, sg_retention_issue_or_pr_28d`.

### `feat_tastemaker` (Tier A; the co-star signal — implement carefully)
1. `int_actor_early_stars` (intermediate): every first star `(actor_id, repo_id, starred_at)` where, at
   `starred_at`, the repo had `< max_stars_total` stars and age ≤ `max_age_days` ("early star").
   `outcome_known_at = starred_at + 60 days`; `hit = stars gained by the repo in (starred_at, starred_at + 60d] >= absolute_min_gain`.
   (Absolute definition on purpose: independent of the snapshot grid and of the relative label.)
2. Per actor, cumulative counts ordered by `outcome_known_at`: `early_stars_known`, `hits_known`.
3. For stargazers of a candidate in `[D-14, D)`, ASOF-join their counts with
   `outcome_known_at < D` (strictly). Smoothed score:
   `tm_score = (hits_known + α) / (early_stars_known + α + β)` with α = 1, β = 50 (tune β so the prior
   mean ≈ base hit rate; record in ADR).
4. Repo features: `sg_tm_mean_14d, sg_tm_max_14d, sg_tm_top_count_14d` (stargazers with
   `early_stars_known >= 5` AND tm_score in the top 1% of such actors as of the last month boundary before D),
   `sg_tm_known_share_14d` (share of stargazers with any known early stars).
Test: a synthetic case where an actor's hit is known only after D must not affect features at D.

### `feat_owner` (Tier A)
Owner = first segment of `repo_name` valid on `D - 1` (display-level identity; accept rename noise).
`owner_prior_repos_seen` (other repos with that owner prefix first seen before D),
`owner_prior_breakouts` (other repos of that owner with `breakout_abs`-style hits known before D,
using the same 60-day absolute rule as tastemaker), `owner_is_org` (org_id present on the repo's events).

### `feat_detail` (Tier B; from `int_issue_response`, `int_pr_lifecycle`, `int_core_actors_daily`)
`detail_coverage_28d` (share of days in window whose events have detail_level = 1),
`issues_opened_28d, issues_closed_28d, issue_close_ratio_28d,
median_first_response_hours_28d` (issues opened in window **and** first response before D;
issues without response before D are excluded from the median),
`share_issues_responded_48h` (among issues opened in `[D-28, D-2)`: responded within 48h and before D),
`prs_opened_28d, prs_merged_28d` (NULL in eras where `pr_merged` is unavailable — see schema audit),
`median_merge_hours_28d, core_actor_count_90d` (distinct actors with maintainer evidence in `[D-90, D)`),
`external_pr_authors_28d` (PR openers in window not in the core set), `tags_created_total_before`,
`era_post_2025_10` (1 if D ≥ 2025-10-07, documents payload trimming).

### `feat_enrich` (Tier C)
`primary_language` (categorical; top 30 languages by frequency in training, else 'Other', NULL → 'Unknown'),
`owner_type` (User/Organization/Unknown), `birth_from_public_event` (birth_source = public event),
`days_api_created_to_birth`.
HN (only if `optional.hn_enabled`): `hn_stories_before_14d, hn_stories_before_3d` (stories created in window,
`created_at < D`), `hn_max_points_aged` (max points among stories created in `[D-30, D-3)`), `hn_any_before`.

## 7.2 Leakage defenses
1. **Time-travel test** — CLI `breakout build leak-test --date D --sample 300`:
   build `mart_repo_features` for `snapshot_dates_mode=single, snapshot_date=D` twice: (a) normal window,
   (b) with `events_end = D` (all inputs truncated at D, including enrichment rows with timestamps ≥ D removed).
   Use a separate DuckDB file for (b). Compare the two outputs for the same `(repo_id, D)`: every column must
   be equal (floats within 1e-9). Run on 3 dates (one pre-2020, one 2024, one after 2025-10-07). Any diff is a bug.
2. **Shuffle check** in Phase 8 (label permutation must give random-level metrics).
3. A dbt singular test asserting that `max(source timestamp used) < snapshot_date` for a sample of rows of each
   feature group (implement by also emitting `_max_input_ts` per group in a debug model, not in the mart).

## 7.3 `config/feature_dictionary.yaml`
For every feature: `name, group, tier (A|B|C), dtype, description, unit, allowed (true/false),
leakage_notes, explain_template`. `explain_template` is a short plain-English phrase with placeholders used
for "why flagged" text, e.g.
```yaml
- name: sg_share_experienced
  group: stargazers
  tier: A
  dtype: float
  description: Share of stars in the last 14 days from accounts with real prior activity
  unit: share
  allowed: true
  leakage_notes: actor activity strictly before star day
  explain_template:
    high: "{pct} of recent stars come from experienced accounts"
    low: "most recent stars come from accounts with little prior activity"
```

## 7.4 Build & export
- CLI `breakout build features --history` builds all `feat_*` + `mart_repo_features` for weekly snapshots,
  joins with labels, and exports `data/derived/training/features_labels/year=YYYY/part-0.parquet`
  plus `training/feature_manifest.json` (feature list, dictionary hash, dbt git sha, row counts per year).
  Upload to the derived HF repo under `training/`.
- CLI `breakout build features --date D` (single mode) writes `data/derived/live/features_D.parquet`
  (used by Phase 9).
- Record in PROGRESS: build time per group, total rows, NULL rate per feature (Tier B NULL rate by year is
  expected to be high before `detail_start_date`).
- Produce `reports/feature_eda.md`: univariate distributions for positives vs negatives for the top 20 features
  (by mutual information or simple AUC), NULL rates by year, and correlation clusters. Small PNGs.

## Acceptance criteria
- [ ] `mart_repo_features` built for history; all dbt tests pass.
- [ ] Leak test passes on 3 dates (paste the summary).
- [ ] Dictionary ↔ columns unit test passes.
- [ ] Training table on HF; `reports/feature_eda.md` committed.
- [ ] Live single-date build for yesterday works and has identical column list/types to the training table.
