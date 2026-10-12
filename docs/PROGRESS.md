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

## Amendments after Phase 1 (ADR-009, 2026-10-12)

| Item | Status | Notes |
|---|---|---|
| `history.trusted_end` / `degraded_end` + `Config.latest_trusted_snapshot()` | ☑ | trusted_end 2025-05-31 as decided; measured onset is 2025-05-24 (open issue below) |
| Capture-quality table + chart (`reports/capture_quality.md`) | ☑ | from BigQuery day tables (the lake only holds one day), 53.8 GB scanned |
| BigQuery re-plan (`docs/bigquery_cost_plan.md`) | ☑ planned, ☐ approved | 564 dry runs; nothing beyond them has run. Needs human decision |
| Multi-source hourly ingest (`ingest.sources`, `source_host`, manifest integrity hooks) | ☑ code, ☐ enabled | OpenDigger `enabled: false` until validation passes |
| Capture-rate validation vs stargazers API (`reports/source_validation.md`) | ☐ blocked | `GH_ENRICH_TOKEN` cannot list stargazers; see open issues |
| OpenDigger license/terms | ☑ searched, ☐ answered | none found for the data; rows tagged `source='opendigger'`, not to be published |
| Daily top-200 API star cross-check + status page alert | ☐ | needs Phase 6/9/10 pieces; client exists (`breakout.enrich.stargazers`) |
| Comment on gharchive.org#320 | see report | |

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

- **Star events collapse in GH Archive since ~2026-03** (ADR-008, `docs/schema_audit.md`
  "Data-volume observations"): WatchEvent is ~25/hour on 2026-08-15 vs ~4,500/hour in 2025-09.
  Decide how to handle before Phase 2 (cutover date) and Phase 6 (labels).
- **Decide `trusted_end`**: measured degradation starts 2025-05-24 (stars 0.71 of baseline vs 0.90 the day
  before), so 2025-05-24..31 sit inside the "trusted" era at ~0.6-0.7 capture. Keep 2025-05-31 or use
  2025-05-23 (ADR-009).
- **Approve the BigQuery schedule** (`docs/bigquery_cost_plan.md`, schedule C recommended) and
  `history.cutover_date` (proposed 2026-09-06).
- **GitHub token for stargazers**: the fine-grained public-read PAT in `GH_ENRICH_TOKEN` gets 403 on
  stargazers (REST and GraphQL). Provide a classic no-scope PAT (or allow use of `gh auth token` for local
  validation). Blocks `reports/source_validation.md` and the OpenDigger go/no-go.
- **OpenDigger data license**: none found; confirm whether OpenDigger-sourced rows may be published to
  the HF dataset (currently excluded). Also confirm OpenDigger is reachable at usable speed from GitHub
  Actions (it was ~6 KB/s from the dev machine) before relying on it for the daily job.
- Post-2025-10-07 PullRequest/Review events have no PR author, creation time or merged flag (ADR-007).
