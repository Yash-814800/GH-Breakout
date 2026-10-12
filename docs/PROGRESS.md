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

## Measured facts

- (Phase 1) 2026-10-10 day: Watch 8,571 / Issues 17,140 / IssueComment 22,725 / PR 40,445 / Review 8,437 / Fork 1,815 / Release 10,562 / Create 74,684 / Public 135 / Push 269,284 (578,948 pushes in 269,284 push_daily rows)
- (Phase 1) Sample-hour (12:00 UTC) WatchEvent counts: 2024-06-03 8,154; 2025-09-01 4,653; 2025-11-03 2,967; 2026-10-10 346
- (Phase 2) Bytes per month, spine-only vs full: see docs/bigquery_cost_plan.md
- (Phase 2) cutover_date:
- (Phase 2) detail_start_date:
- (Phase 3) Lake size on HF (GB), file count:
- (Phase 6) Candidates per snapshot (median), positive rate:
- (Phase 8) Baseline vs model PR-AUC / precision@25 (pooled and per year):
- (Phase 9) Daily job runtime (median):

## Open issues / TODO for the human

- **Star events collapse in GH Archive since ~2026-03** (ADR-008, `docs/schema_audit.md`
  "Data-volume observations"): WatchEvent is ~25/hour on 2026-08-15 vs ~4,500/hour in 2025-09.
  Decide how to handle before Phase 2 (cutover date) and Phase 6 (labels).
- Post-2025-10-07 PullRequest/Review events have no PR author, creation time or merged flag (ADR-007).
