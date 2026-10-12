# Progress

Update this file at the end of every phase: tick the box, add the date, and record numbers you
measured (row counts, sizes, runtimes, metrics). Future sessions rely on it.

| Phase | Title | Status | Date | Notes |
|---|---|---|---|---|
| 00 | Bootstrap & guardrails | ☑ | 2026-10-12 | 26 tests pass; ruff, mypy, pre-commit (incl. gitleaks) green locally. CI green on GitHub (run 38189757833). |
| 01 | Schema audit, slim schema, hourly parser | ☐ | | |
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

- (Phase 2) Bytes per month, spine-only vs full: see docs/bigquery_cost_plan.md
- (Phase 2) cutover_date:
- (Phase 2) detail_start_date:
- (Phase 3) Lake size on HF (GB), file count:
- (Phase 6) Candidates per snapshot (median), positive rate:
- (Phase 8) Baseline vs model PR-AUC / precision@25 (pooled and per year):
- (Phase 9) Daily job runtime (median):

## Open issues / TODO for the human
