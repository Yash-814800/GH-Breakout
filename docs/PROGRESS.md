# Progress

Update this file at the end of every phase: tick the box, add the date, and record numbers you
measured (row counts, sizes, runtimes, metrics). Future sessions rely on it.

| Phase | Title | Status | Date | Notes |
|---|---|---|---|---|
| 00 | Bootstrap & guardrails | ☑ | 2026-10-12 | 26 tests pass; ruff, mypy, pre-commit (incl. gitleaks) green locally. CI green on GitHub (run 38189757833). |
| 01 | Schema audit, slim schema, hourly parser | ☑ | 2026-10-12 | 9 eras audited; day 2026-10-10 ingested: 24/24 hours ok, 763,462 rows, 39 s wall clock, 12 MB lake + 24 MB staging; rerun no-op (0.5 s, files checksum-identical). See open issue on star volume. |
| 02 | BigQuery cost plan & historical backfill | ☑ | 2026-10-13 | Spine 2015-01..2023-05 complete: 498/498 units, 101/101 months finalized, 0 failed, 522.7 GB billed, 57 GB lake (3.26 G events). Re-run performs 0 queries; `lake verify` OK (963 files). Parity PASS (2024-06-03, 2026-10-10). Hourly era from 2023-06-01 runs in Actions (ADR-011). Lake lives on the Lexar SSD, symlinked from `data/lake` (ADR-012). |
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
| Source test from a GitHub Actions runner | ☑ NO-GO | OpenDigger ~0.01 MB/s from the runner (needs >= 1), manifests 404; gharchive 54 MB/s. `reports/source_validation.md`, run 38194688025 |
| Stargazers API for per-repo ground truth | ✖ not available | GitHub restricted it to admins/collaborators in July 2026 (ADR-010) |
| Live-source gate / item 5 | ☐ not started | waits for your review of the source test |

## Measured facts

- (Phase 1) 2026-10-10 day: Watch 8,571 / Issues 17,140 / IssueComment 22,725 / PR 40,445 / Review 8,437 / Fork 1,815 / Release 10,562 / Create 74,684 / Public 135 / Push 269,284 (578,948 pushes in 269,284 push_daily rows)
- (Phase 1) Sample-hour (12:00 UTC) WatchEvent counts: 2024-06-03 8,154; 2025-09-01 4,653; 2025-11-03 2,967; 2026-10-10 346
- (ADR-009) Capture vs 2024 same-weekday median (stars): 2025-05-23 0.90, 2025-05-24 0.71; monthly medians 2025-06 0.64, 2025-10 0.44, 2026-02 0.37, 2026-05 0.12, 2026-07 0.01, 2026-09 0.06
- (ADR-009) BigQuery dry runs: spine all history 994 GB; full all history 32.3 TB; full for 2023-06..2025-05 10.5 TB; 9 day tables missing
- (ADR-009) Hourly-file download for those 24 months ~1.5 TB (sampled Content-Length)
- (ADR-009/010) OpenDigger hour files 214-446 MB; ~6 KB/s from the dev machine, ~10 KB/s from a GitHub Actions runner (US), vs 4.5 MB/s (dev) and 54 MB/s (runner) for data.gharchive.org; manifests 404
- (ADR-010) BigQuery spine 2015-01..2023-05: 522.4 GB, 101 months, 9 missing day tables (4 recoverable from hourly files)
- (ADR-010) Measured day 2024-06-03 via the hourly path (2 hour-workers): 5 min 6 s wall, ~3.1 GB download, 24/24 ok, 2.67 M rows kept (Watch 208,983), lake +59 MB, staging 112 MB. Extrapolation for ~723 trusted days: ~30 h wall at 2 workers, ~45 GB lake, ~80 GB staging if kept
- (ADR-010) data.gharchive.org WatchEvents per hour 2026-10-11 21-23 UTC: 169, 179, 213
- (Phase 2) Bytes per month, spine-only vs full: see docs/bigquery_cost_plan.md
- (Phase 2) cutover_date: 2023-06-01 (ADR-010)
- (Phase 2) Parity (BigQuery full vs hourly parser): 2024-06-03 and 2026-10-10, 0 differing rows or columns on every event type and push_daily; billed 19.57 GB and 0.89 GB
- (Phase 2) detail_start_date: 2023-06-01 (ADR-010)
- (Phase 2) BigQuery spine 2015-01..2023-05: 522.7 GB billed in this run (incl. an 11.7 GB first slice) of the 900 GB monthly budget; this calendar month in total about 600 GB with the 55 GB used earlier and the two parity days (20.5 GB). Nothing remains to scan; no resume date.
- (Phase 2) Local lake: 57 GB on disk, 963 parquet files, 3,263,437,726 events rows (incl. 453,798 from Phase 1 test days). Rows per event type per year (millions):

| year | Create | Fork | IssueComment | Issues | Public | PullRequest | Review | Release | Watch | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 28.4 | 7.0 | 19.1 | 9.9 | 0.2 | 10.8 | 0.0 | 0.7 | 18.9 | 95 |
| 2016 | 43.8 | 9.5 | 25.7 | 12.8 | 0.3 | 17.8 | 0.0 | 1.1 | 26.1 | 137 |
| 2017 | 57.2 | 11.8 | 29.3 | 14.9 | 0.4 | 22.9 | 0.0 | 1.5 | 32.6 | 171 |
| 2018 | 66.7 | 12.8 | 31.1 | 16.4 | 0.5 | 27.6 | 0.0 | 1.9 | 37.0 | 194 |
| 2019 | 86.9 | 16.4 | 38.3 | 18.8 | 1.6 | 45.5 | 0.0 | 2.4 | 46.1 | 256 |
| 2020 | 134.7 | 18.7 | 54.2 | 25.7 | 2.6 | 84.5 | 8.9 | 4.2 | 49.4 | 383 |
| 2021 | 149.0 | 17.7 | 55.4 | 23.2 | 3.1 | 92.5 | 24.3 | 5.3 | 49.1 | 420 |
| 2022 | 201.8 | 19.4 | 69.4 | 25.4 | 3.9 | 129.8 | 30.1 | 7.0 | 56.5 | 543 |
| 2023 (to May) | 79.5 | 8.3 | 27.9 | 12.0 | 2.0 | 47.4 | 14.2 | 3.2 | 34.7 | 229 |

  push_daily rows (M) / pushes (M): 2015 37.3/104; 2016 52.3/165; 2017 67.4/219; 2018 79.3/258; 2019 92.8/313; 2020 120.6/434; 2021 131.7/490; 2022 169.4/662; 2023 82.5/317.
- (Phase 3) Lake size on HF (GB), file count:
- (Phase 6) Candidates per snapshot (median), positive rate:
- (Phase 8) Baseline vs model PR-AUC / precision@25 (pooled and per year):
- (Phase 9) Daily job runtime (median):

## Open issues / TODO for the human

- ADR-011: hourly backfill moves to a GitHub Actions matrix (built in Phase 3); nothing heavy runs locally. Needs the `HF_TOKEN` Actions secret then. `data/staging` (5.4 GB) is safe to delete.

- ~~Approve the BigQuery spine extraction~~ done 2026-10-13.
- ~~Lake size over 60 GB~~ accepted (ADR-013). ~~HF_TOKEN Actions secret~~ set 2026-10-13. ~~Dataset license~~ MIT (ADR-013). Still open: copyright-holder name for a `LICENSE` file; `HF_USER` as an Actions variable when the workflow is written.
- Review the source-test result (NO-GO for OpenDigger) and tell me how to proceed with the live-source gate (ADR-010, item 5). I have not started item 5.
- The stargazers listing is no longer available to us (ADR-010); the capture check and the daily
  cross-check must use `stargazerCount` deltas instead.
- OpenDigger data license: none found; its rows stay out of the public dataset.
- Post-2025-10-07 PullRequest/Review events have no PR author, creation time or merged flag (ADR-007).
