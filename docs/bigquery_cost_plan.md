# BigQuery cost plan and backfill schedule (ADR-010)

Generated 2026-10-12. Supersedes the Phase 2 default and the earlier schedules in ADR-009. **Approved split (human, 2026-10-12): BigQuery spine only for 2015-01-01..2023-05-31; everything from `history.cutover_date` = 2023-06-01 comes from data.gharchive.org hourly files through the Phase 1 parser.** Nothing in the range below has been run; only dry runs.

## 1. BigQuery spine, 2015-01..2023-05 (dry-run, to be approved before running)

- Range: 2015-01-01 .. 2023-05-31 (101 calendar months), mode `spine`
- Dry-run bytes, **one query over the whole range: 522.4 GB**; sum of the 101 per-month queries: 522.4 GB (identical: bytes are additive per table)
- Monthly budget `bigquery.monthly_budget_bytes`: 900 GB; already spent this calendar month (2026-10): 55.2 GB
- **Fits in one calendar month:** 577.6 GB of 900 GB (64%), leaving 322 GB headroom in 2026-10. No split across months needed.
- Per-query cap `per_query_max_bytes_billed` 250 GB; largest month 2022-10 is 11.7 GB, so 7-day chunks are far below it
- PushEvent rows ride in the same query (columns already scanned) and are aggregated into `push_daily` locally, so no separate push query is run
- 9 days have no `githubarchive.day` table (2015-12-31, 2020-08-22, 2021-05-08, 2021-05-10, 2021-05-11, 2021-08-26, 2021-10-26, 2021-10-27, 2021-10-28). Probed 2026-10-12: 2015-12-31, 2021-05-08, 2021-05-10, 2021-05-11 exist as hourly files (24/24 hours) and are listed in `history.hourly_gap_days` (fetched through the hourly parser although before the cutover); 2020-08-22, 2021-08-26, 2021-10-26/27/28 exist in neither source nor in the month tables (checked, 1.5 GB scanned) and stay empty. 2021-08-27 and 2021-10-25 are partial days (80k and 58k events)

### Per-year bytes (GB scanned, spine)

| year | GB |
|---|---:|
| 2015 | 18.4 |
| 2016 | 28.1 |
| 2017 | 36.4 |
| 2018 | 42.7 |
| 2019 | 54.9 |
| 2020 | 79.9 |
| 2021 | 89.1 |
| 2022 | 118.8 |
| 2023 | 54.2 |
| **total** | **522.4** |

## 2. Hourly files from the cutover onward (laptop, no BigQuery quota)

- Order: trusted era 2023-06-01..2025-05-23 first, then the degraded era the day after 2025-05-23 .. last complete day (kept, flagged, never trained or evaluated on). Within an era oldest to newest.
- `breakout backfill hourly [--dry]`: resumable through the hourly manifest (hours already `ok` at the current parser version are skipped), at most 4 concurrent downloads (`--workers`, default 2).
- Estimated download (sampled `Content-Length`, compressed): trusted era ~1,457 GB (2023-06..2025-04) plus May 2025 up to the 23rd; degraded era ~532 GB. Order of magnitude: **~2 TB total**.
- Disk: day files are ZSTD parquet; staging is currently kept (about 2x the day file). A measured day is recorded in `docs/PROGRESS.md`. Plan on a few hundred GB with staging, or add staging cleanup after the day build before running the full range.

## 3. Resulting coverage

| period | source | detail_level | era |
|---|---|---|---|
| 2015-01-01 .. 2023-05-31 | BigQuery spine (`bq-YYYYMM.parquet`) | 0 | trusted |
| 2023-06-01 .. 2025-05-23 | hourly files (`day-*.parquet`) | 1 | trusted |
| 2025-05-23 + 1 .. last complete day | hourly files | 1 | degraded (flag, never train/evaluate) |

`history.detail_start_date` = 2023-06-01: Tier B features are NaN before it. The first trusted snapshot with a full 160-day detail look-back is therefore 2023-11-08; earlier snapshots rely on Tier A.

## 4. Decision requested

Approve running the 522.4 GB spine extraction this calendar month (2026-10). Until then nothing is executed.
