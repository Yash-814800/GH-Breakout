# Progress

Update this file at the end of every phase: tick the box, add the date, and record numbers you
measured (row counts, sizes, runtimes, metrics). Future sessions rely on it.

| Phase | Title | Status | Date | Notes |
|---|---|---|---|---|
| 00 | Bootstrap & guardrails | ☑ | 2026-10-12 | 26 tests pass; ruff, mypy, pre-commit (incl. gitleaks) green locally. CI green on GitHub (run 38189757833). |
| 01 | Schema audit, slim schema, hourly parser | ☑ | 2026-10-12 | 9 eras audited; day 2026-10-10 ingested: 24/24 hours ok, 763,462 rows, 39 s wall clock, 12 MB lake + 24 MB staging; rerun no-op (0.5 s, files checksum-identical). See open issue on star volume. |
| 02 | BigQuery cost plan & historical backfill | ☐ | | |
| 03 | Lake on Hugging Face (layout, upload, sync, compaction) | ☐ | | |
| 04 | Enrichment (repo metadata, actor age, trending, HN) | ☐ | | |
| 05 | dbt staging & intermediate models | ☐ | | |
| 06 | Candidates, labels, baseline, evaluation harness | ☐ | | |
| 07 | Point-in-time feature marts | ☐ | | |
| 08 | LightGBM, calibration, SHAP, model registry | ☐ | | |
| 09 | Daily pipeline, weekly retrain, health checks | ☐ | | |
| 10 | Website (Astro) + deploy | ☐ | | |
| 11 | Fake-star detector, similar repos, cohort retention | ☐ | | |
| 12 | Distribution (RSS, badges, digest, Bluesky) | ☐ | | |
| 13 | Portfolio polish, dbt docs, ClickHouse benchmark, final audit | ☐ | | |

## Amendments after Phase 1 (ADR-009, ADR-010, 2026-10-12)

| Item | Status | Notes |
|---|---|---|
| `GH_ENRICH_TOKEN` classic no-scope PAT, 1-year expiry | ☑ set locally; ☐ Actions secret | `.env` updated and verified (5,000 req/h, no scopes). Actions secret is yours to set. Rotation reminder in `docs/runbook.md` (expires 2027-10-12) |
| `history.trusted_end = 2025-05-23`, `latest_trusted_snapshot` 2025-04-24 | ☑ | `degraded_end` removed; degraded era runs to `live.source_start` (null) |
| `history.cutover_date = 2023-06-01`, `detail_start_date = 2023-06-01`, `hourly_gap_days` | ☑ | |
| `live.source` / `live.source_start` | ☑ keys, both null | switch gated on source test + human approval |
| BigQuery spine 2015-01..2023-05 dry run | ☑ 522.4 GB, ☐ approved to run | `docs/bigquery_cost_plan.md`; fits this calendar month with 55 GB already used |
| `breakout backfill hourly` (trusted first, <= 4 downloads, resumable) | ☑ code, ☐ run | ~2 TB download (trusted ~1.5 TB, degraded ~0.5 TB) |
| `breakout lake verify` + invariants | ☑ | ADR-010 |
| `live_available` in `config/feature_dictionary.yaml` + validator | ☑ | entries arrive in Phase 7; the file already validates |
| Provisional-window logic (`Config.window_is_provisional`) | ☑ | leaderboard flag + methodology wording land with Phase 7/10 |
| Capture-quality report re-rendered for `trusted_end` 2025-05-23 | ☑ | `reports/capture_quality.md` |
| Source test from a GitHub Actions runner | see `reports/source_validation.md` | run 38194688025 |
| Stargazers API for per-repo ground truth | ✖ not available | GitHub restricted it to admins/collaborators in July 2026 (ADR-010) |
| Live-source gate / item 5 | ☐ not started | waits for your review of the source test |

## Measured facts

- (Phase 1) 2026-10-10 day: Watch 8,571 / Issues 17,140 / IssueComment 22,725 / PR 40,445 / Review 8,437 / Fork 1,815 / Release 10,562 / Create 74,684 / Public 135 / Push 269,284 (578,948 pushes in 269,284 push_daily rows)
- (Phase 1) Sample-hour (12:00 UTC) WatchEvent counts: 2024-06-03 8,154; 2025-09-01 4,653; 2025-11-03 2,967; 2026-10-10 346
- (ADR-009) Capture vs 2024 same-weekday median (stars): 2025-05-23 0.90, 2025-05-24 0.71; monthly medians 2025-06 0.64, 2025-10 0.44, 2026-02 0.37, 2026-05 0.12, 2026-07 0.01, 2026-09 0.06
- (ADR-009) BigQuery dry runs: spine all history 994 GB; full all history 32.3 TB; full for 2023-06..2025-05 10.5 TB; 9 day tables missing
- (ADR-009) Hourly-file download for those 24 months ~1.5 TB (sampled Content-Length)
- (ADR-009) OpenDigger hour files 214-446 MB; throughput from dev machine ~6 KB/s vs 4.5 MB/s for data.gharchive.org; manifests 404
- (Phase 2) Bytes per month, spine-only vs full: see docs/bigquery_cost_plan.md
- (Phase 2) cutover_date:
- (Phase 2) detail_start_date:
- (Phase 3) Lake size on HF (GB), file count:
- (Phase 6) Candidates per snapshot (median), positive rate:
- (Phase 8) Baseline vs model PR-AUC / precision@25 (pooled and per year):
- (Phase 9) Daily job runtime (median):

## Open issues / TODO for the human

- Set the GitHub Actions secret `GH_ENRICH_TOKEN` (the PAT works locally; the runner test did not need it).
- Approve running the 522.4 GB BigQuery spine extraction (this calendar month, 578 GB of 900 GB).
- Review the source-test result and decide the live-source gate (ADR-010, item 5).
- The stargazers listing is no longer available to us (ADR-010); the capture check and the daily
  cross-check must use `stargazerCount` deltas instead.
- OpenDigger data license: none found; its rows stay out of the public dataset.
- Post-2025-10-07 PullRequest/Review events have no PR author, creation time or merged flag (ADR-007).
