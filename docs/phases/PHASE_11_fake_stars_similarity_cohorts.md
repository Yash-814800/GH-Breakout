# Phase 11 — Suspicious-growth (fake-star) detector, similar repos, cohort retention, insights

## Goal
Add the features that make the project stand out:
1. A transparent **suspicious-growth score** so the leaderboard can't be gamed by farmed stars.
2. **Similar repos** via item-item co-star similarity.
3. **Cohort retention** ("stars vs real adoption") on repo pages.
4. An **insights** page with a few data stories from the full history.

## Prerequisites
Phases 05–10 done (stargazer enrichment, daily pipeline, site).

## 11.1 Suspicious-growth score — `src/breakout/detect/` + dbt `mart_suspicion`
Grain `(repo_id, snapshot_date)` for candidates (same point-in-time rules as features).
**Signals** over first stars in `[D-14, D)` (most already exist in `feat_stargazers`; reuse, don't duplicate SQL —
factor shared CTEs into intermediate models if needed):
- `s_new_accounts`: share of stargazers with estimated account age < 30 days (and < 7 days)
- `s_inactive`: share with zero activity in the 90 days before their star
- `s_bulk`: share who starred ≥ 50 repos that UTC day
- `s_burst`: max share of the window's stars landing in a single hour; and the coefficient of variation of
  inter-arrival times within the top burst hour (very regular spacing is machine-like)
- `s_lockstep`: share of stargazers who also starred ≥ 3 of the same other repos within ±24 h of starring this one
  (co-starring "rings"; compute with a self-join on stars within the window, restricted to this repo's
  stargazers; cap stargazers per repo at 5,000 by most recent to bound cost)
- `s_no_engagement`: stars_14d large while forks + issues + PRs + comments in the window are ~0 (define as
  `1 - min(1, engagement_events / (0.05 * stars_14d))`)
**Score**: for each signal compute a robust z-score against all candidates on the same D
(`(x - median) / (1.4826 * MAD)`, clipped to [0, 6]), combine as a weighted sum with documented weights
(start equal; tune only if labeled data exists), map to 0–100 via the empirical CDF of historical scores.
Emit `suspicion_score`, `suspicion_level` (low/medium/high at the 90th/98th percentiles), and up to 3
`reason_codes` with human-readable text (e.g. "61% of new stars are from accounts younger than 30 days").
**Validation**:
- Search for the public dataset from the 2024 study on suspected fake GitHub stars (the "StarScout" work by
  researchers at CMU and collaborators). If it is downloadable and its license permits, use its repo/actor
  labels to measure precision/recall of the score on overlapping repos and dates; record source and license in
  an ADR. If unavailable, produce a sample of the 40 highest-scored historical candidates with their signals and
  ask the human to spot-check them (do not label on their behalf).
- Report prevalence by year and how many historical `breakout_rel` positives were high-suspicion.
- Ablation (Phase 8 harness): retrain with high-suspicion positives relabeled as negatives; report the effect.
  Keep whichever label policy the human chooses (HUMAN DECISION) and record it.
**Integration**: daily pipeline fills the reserved `suspicion_score` column in predictions; leaderboard shows a
neutral badge ("unusual star pattern") with a tooltip of reasons and the "hide suspicious" filter; repo page shows
the signal breakdown. Wording must be non-accusatory ("unusual", "may indicate"), and the About page explains
how owners can request review (issue template `.github/ISSUE_TEMPLATE/review-request.md`).
Do **not** feed `suspicion_score` itself into the model (its inputs already are features).

## 11.2 Similar repos — dbt `mart_similar_repos` (weekly reference + daily lookup)
- **Reference index** (weekly workflow, add a step): repos with ≥ 50 stars in the last 365 days. For each,
  keep up to 2,000 most recent stargazers, excluding bots and bulk starrers (≥ 50 stars/day). Requires pulling
  ~12 months of `WatchEvent` in the weekly job — measure disk/time; if too large, use 180 days. Store
  `derived/similarity/reference_stargazers.parquet` (`repo_id, actor_id`) and `reference_repo_sizes.parquet`.
- **Daily lookup** for leaderboard repos: their stargazers (same exclusions) joined to the reference on `actor_id`;
  `cosine = overlap / sqrt(n_a * n_b)`; keep top 5 with `overlap >= 5`, excluding the repo itself and its forks.
  Output `repo_id, similar_repo_id, overlap, cosine, similar_repo_name (latest), similar_language`.
- Show on repo pages ("People who starred this also starred…"), linking to GitHub.
- Unit-test cosine on a tiny synthetic example; dbt test that cosine ∈ (0, 1].

## 11.3 Cohort retention on repo pages
- Use `int_star_cohort_retention` / `int_stargazer_later_actions` (Phase 5), computed in window mode for
  leaderboard repos. Export per repo: weekly star cohorts (up to 12 weeks) × share who later forked / opened an issue
  or PR / commented within 30 days (only cohorts whose 30 days have elapsed).
- Add a reference band: the median and IQR of the same metric for historical `breakout_rel` positives at the same
  repo age (precomputed from history once; stored in `derived/reference/retention_reference.parquet`).
- Repo page: small heatmap (cohort week × action type) + "compared with past breakouts" text.

## 11.4 `/insights/` page (history-based data stories, regenerated monthly)
Compute once from the history build (`breakout publish insights`), store small JSONs, render with Plot:
1. **Stars vs adoption**: retention curves for repos that broke out and stayed active vs. those that spiked and faded.
2. **The AI-era shift**: candidates and breakouts per year by language; share of breakouts in AI/LLM-related repos
   (use language + description keywords for display only — never as model features).
3. **Lead time**: distribution of days between our (backtest) first flag and the first Trending appearance.
4. **Unusual star patterns over time**: prevalence of high suspicion by year.
Each story: one chart, three sentences, and the SQL that produced it (collapsible) — this showcases the SQL work.

## Acceptance criteria
- [ ] `mart_suspicion` built for history and daily; validation report `reports/suspicion.md` with prevalence,
      validation results (or the human spot-check list), and the ablation.
- [ ] Leaderboard shows badges + filter; repo pages show suspicion breakdown, similar repos, retention heatmap.
- [ ] Weekly job builds the similarity reference within its time budget (report runtime and disk).
- [ ] `/insights/` live with 4 stories.
- [ ] dbt tests pass; unit tests for robust z-scores and cosine pass.
