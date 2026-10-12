# Phase 09 — Daily pipeline, weekly retrain, monthly maintenance, health checks (GitHub Actions)

## Goal
Run everything automatically, for free, on GitHub Actions standard runners (public repo):
- **Daily**: ingest new GH Archive hours (with gap detection), update the lake, enrich, rebuild
  features for candidates only, score with the champion model, freeze predictions immutably,
  append to the tamper-evident ledger, compute matured outcomes, export site data, report status.
- **Weekly**: append newly matured training rows, retrain, champion/challenger promotion, drift report.
- **Monthly**: compaction, actor-age map top-up, metadata refresh.
- **Health**: detect stale runs and open a GitHub issue (free email notification).

## Prerequisites
Phases 01–08 done; champion model exists; `HF_TOKEN`, `HF_USER`, `GH_ENRICH_TOKEN` configured as
Actions secrets/vars (HUMAN_SETUP step 5); workflow permissions set to read/write.

## Facts to design around
- Public-repo standard Linux runner: 4 vCPU, 16 GB RAM, ~14 GB free SSD (more after removing
  preinstalled toolchains), 6-hour job limit, free unlimited minutes.
- Scheduled runs may be delayed or occasionally skipped; cron is UTC. Design so any run catches up.
- Scheduled workflows are disabled after 60 days without repository activity → the daily job commits
  the ledger/heartbeat, and the health workflow also re-enables workflows defensively.

## 9.1 State that must persist between runs (all on Hugging Face, never only in the runner)
- Hourly manifest + catalog (events repo).
- `derived/state/tastemaker_state.parquet` — per actor `early_stars_known, hits_known, as_of`.
- `derived/state/owner_state.parquet` — per owner prefix `prior_repos_seen, prior_breakouts, as_of`.
- `derived/enrich/*` (metadata, actor-age map, trending, HN).
- `derived/live/features/date=D.parquet` — the exact features scored each day (becomes training data).
- `snapshots/predictions/date=D/predictions.parquet` and `snapshots/outcomes/date=D/outcomes.parquet`.
- Initialize the two state tables at the end of this phase's setup from the Phase 7 history build
  (`breakout build state --as-of <cutover or latest history date>`), and implement the incremental
  update (9.2 step 6). In history mode `feat_tastemaker`/`feat_owner` compute counts from scratch; in
  daily mode they read state + increment. **The parity test (9.6) proves both paths agree.**

## 9.2 `breakout daily run [--date D] [--skip-deploy-data]` (one Python orchestrator)
Each step is idempotent, timed, logged, and recorded in `data/run/status.json`. On error: record the
failure, continue with independent steps where safe, and exit non-zero at the end.
1. **Plan**: `D = today UTC` unless given. Pull manifest + catalog from HF. Days to (re)ingest =
   days in `[cutover_date, D-1]` that have hours needing work (`manifest.hours_needing_work`) —
   this includes late hours within `late_hour_retry_days` and any missed days from skipped runs.
   Cap at 10 days per run (log if capped; the next run continues).
2. **Ingest** each such day with `ingest_day` (Phase 1). Only hours that ended ≥ `min_hour_lag` ago.
3. **Publish lake**: upload changed day files + manifest + catalog in batched commits.
4. **Compact** the previous month if: today ≥ 4th of the month, it is not compacted, and it has no
   `pending` hours (Phase 3 `lake compact`).
5. **Working set**: `lake pull` for `[D - recent_window_days, D)` for all raw types + push_daily, and
   pull state/enrichment files. Free disk first (workflow step). Delete the staging directory after use.
   Disk strategy: `WatchEvent` and `push_daily` are needed in full (candidate detection, early stars).
   For the other types, if projected disk use exceeds 60% of free space, **stream-and-filter**: download one
   file at a time, keep only rows for the young-moving repo set and their stargazers (computed first from
   `WatchEvent`), write the filtered file, delete the original. Log disk usage (`shutil.disk_usage`) per step.
6. **State increment**: update tastemaker/owner state with outcomes that became known in
   `[state.as_of, D)` (early stars from `[as_of - 60d, D - 60d)`, all inside the window). Upload new state.
   If `state.as_of` is so old that `as_of - 60d - 14d` falls before the pulled window (e.g. runs were skipped for
   weeks), pull the extra WatchEvent days needed first; never silently skip outcomes.
7. **Enrich**: compute the preliminary candidate superset (stars-only query on the window), fetch
   GitHub metadata for repos missing or stale (> 30 days) — metadata is required for correct `birth_at`
   in window mode; fetch trending for today (if allowed), HN for the last 3 days.
8. **dbt**: `dbt source freshness` (record result), then
   `dbt build --select +mart_repo_features --vars '{events_start: D-recent_window_days, snapshot_dates_mode: single, snapshot_date: D}'`.
   Test failures with `severity: error` fail the run before scoring.
9. **Score**: `registry.load_champion()`; predict all candidates of D; rank by calibrated probability;
   compute explanation sentences for the top `site.leaderboard_size * 2`. Write
   `data/run/predictions_D.parquet` with: `snapshot_date, repo_id, repo_name, rank, prob, raw_score,
   b1_rank` (baseline B1 rank on the same candidates — so the live track record can compare model vs
   baseline from day one; frozen files can never gain columns later), `explanation, top_contribs (JSON),
   model_version, features_hash, schema_version`. Reserve a nullable `suspicion_score` column now
   (filled from Phase 11 on) for the same reason. Save the feature rows as
   `live/features/date=D.parquet` (derived repo).
10. **Freeze**: upload predictions to `snapshots/predictions/date=D/predictions.parquet` **only if it does not
    exist**. If it exists with the same content hash → no-op. If it exists with a different hash → do not
    overwrite; record `freeze_conflict` in status (alert via health check). Never delete snapshots.
11. **Ledger**: append one row to `ledger/predictions.csv`:
    `date, model_version, n_candidates, file_sha256, top50_repo_ids_sha256, hf_commit, prev_row_hash, row_hash`
    where `row_hash = sha256(prev_row_hash + "|" + all other fields)`. Skip if a row for D exists with the
    same `file_sha256`. Provide `breakout ops verify-ledger` that re-downloads snapshots and verifies the chain.
12. **Outcomes**: for snapshot `M = D - horizon_days` (and any earlier matured date missing outcomes), compute
    realized `gain_30d`, labels (same SQL as `mart_labels`), and first Trending date; upload
    `snapshots/outcomes/date=M/outcomes.parquet` (never modify predictions files).
13. **Site data**: `breakout publish site-data` (implemented minimally now, extended in Phase 10) writes
    `site/public/data/leaderboard.json` and `site/public/data/status.json`.
14. **Heartbeat**: write `status/heartbeat.json` (`last_success_at`, `D`, `model_version`, counts, runtime).
15. **Commit**: `git add ledger/ status/` and commit as `github-actions[bot]`
    (`chore(daily): predictions for D`); `git pull --rebase` + push with 3 retries.

## 9.3 Workflows (`.github/workflows/`)
Common: pin third-party actions to full commit SHAs (comment the version), `permissions` minimal per job,
`timeout-minutes`, `concurrency: {group: pipeline, cancel-in-progress: false}` shared by daily/weekly/monthly
so they never run at the same time. Setup steps: checkout, free disk space (remove
`/usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL` and prune docker images;
log `df -h` before/after), `astral-sh/setup-uv` with cache, `uv sync --frozen`.
- `daily.yml`: `schedule: cron "17 3 * * *"` + `workflow_dispatch` (inputs: `date`, `skip_deploy`).
  Permissions: `contents: write`. Runs `uv run breakout daily run`. Uploads `data/run/status.json` and logs as
  an artifact (retention 14 days). Phase 10 adds the site build + deploy job (`needs: pipeline`).
- `weekly.yml`: Sundays `cron "41 5 * * 0"` + manual. Steps:
  1. `breakout ml append-live-training` — for Mondays whose labels matured since the last run, join
     `live/features/date=Monday` with labels computed from the window → append to
     `training/features_labels/year=YYYY/live-YYYYMMDD.parquet`.
  2. `breakout ml train-final --candidate` (data: latest `final_train_years`; negatives subsampled if needed).
  3. `breakout ml promote --if-better` (registry rule from Phase 8). Write `reports/retrain/YYYY-MM-DD.md`
     and commit it.
  4. `breakout ops drift` — PSI per feature: last 4 weeks of live features vs the champion's training
     distribution (10 quantile bins from training); flag PSI > 0.25. Write `derived/ops/drift.json`.
- `monthly.yml`: 2nd of month `cron "29 4 2 * *"`: actor-age map top-up (~200 new high ids), metadata refresh
  for repos on the leaderboard in the last 90 days, `lake verify`, HF storage usage report.
- `health.yml`: every 6 h `cron "7 */6 * * *"`. Read `status/heartbeat.json` from the default branch. If
  `last_success_at` older than 30 h, or status shows `freeze_conflict`, missing hours older than 3 days, or
  failed dbt freshness → open or update a single issue titled "Pipeline health alert" (label
  `pipeline-health`) with details using `gh issue` (`permissions: issues: write`). Close it automatically when
  healthy again. Also run `gh workflow enable daily.yml weekly.yml monthly.yml` (harmless if already enabled;
  `permissions: actions: write`) as a keepalive.
- `backfill-day.yml`: `workflow_dispatch` with `start`/`end` dates to re-ingest a range (manual repair).

## 9.4 Runtime budget
Target: daily job < 60 min, hard cap `daily.max_runtime_minutes`. Log per-step durations in status. If
the working-set pull dominates, consider `actions/cache` for the previous day's window files keyed by
date (remember the 10 GB repo cache limit) — measure before adding.

## 9.5 Local equivalents
`make daily DATE=YYYY-MM-DD` runs the same orchestrator locally with `--no-commit --no-upload` flags
(dry mode writes to a temp HF-free directory). Use this to debug before pushing workflow changes.

## 9.6 Training/serving parity test (must pass before enabling the schedule)
`breakout ops parity --date D0` for a historical Monday `D0` inside the history range (≥ cutover is better if
available): run the daily orchestrator's feature path in window mode for `D0` (no uploads), and compare with
the history-built `mart_repo_features` rows for `D0`. Requirements: same candidate set (Jaccard ≥ 0.99; list
differences and explain them), feature values equal within 1e-6 for ≥ 99% of cells per feature, and
prediction rank correlation ≥ 0.99. Fix discrepancies (typically birth/left-censoring or state increments).
Write `docs/parity_daily_vs_history.md`.

## Acceptance criteria
- [ ] Parity test passes and its report is committed.
- [ ] Manual `workflow_dispatch` of `daily.yml` succeeds end to end; a snapshot file and a ledger row exist.
- [ ] A second manual run the same day is a no-op for ingestion/freeze/ledger (idempotency).
- [ ] Simulated gap: delete one hour from the manifest locally (or use a test double) → next run re-ingests it.
- [ ] `weekly.yml` and `monthly.yml` succeed when dispatched manually; `health.yml` opens an issue when
      the heartbeat is artificially stale (test on a branch) and closes it when healthy.
- [ ] `breakout ops verify-ledger` passes.
- [ ] `docs/runbook.md` updated: how to rerun a day, repair gaps, roll back a model (point champion to a previous
      version), and what each alert means.
