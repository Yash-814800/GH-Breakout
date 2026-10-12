# BigQuery cost plan (revised for the trusted era)

Generated 2026-10-12 from `breakout backfill survey` (564 dry runs, free) over 2015-01-01..2026-09-05. Machine-readable: `data/manifests/bq_cost_survey.json` (git-ignored). Supersedes the Phase 2 default policy per ADR-009: full detail targets the 24 months ending 2025-05 (the trusted era), not the most recent 24 months. **Nothing has been run; this needs a human decision (see the end).**

## Key numbers

- Spine mode, **all** 141 months: **994 GB** (about one quota month).
- Full mode (payload parsed), all months: 32.3 TB; the 24 trusted months alone: **10.52 TB**. Full mode costs ~30-40x spine in the trusted era because `payload` dominates.
- Monthly sandbox quota: 1 TB; project budget 900 GB/month. Already spent in 2026-10: 54 GB (capture-quality query, `reports/capture_quality.md`).
- A separate `push_daily` query (687 GB) is redundant: PushEvent rows ride in the same query (their columns are already scanned) and are aggregated locally. `spine_no_push` equals `spine` byte for byte (a `type` filter never reduces bytes).
- 9 day tables are absent from `githubarchive.day` (2015-12-31, 2020-08-22, 2021-05-08, 2021-05-10, 2021-05-11, 2021-08-26, 2021-10-26, 2021-10-27, 2021-10-28); the months containing them are slightly under-counted below and need the month-table fallback at run time.
- Alternative for detail: hourly files from data.gharchive.org for the same 24 months are about **1,531 GB** of download (sampled `Content-Length`; no BigQuery quota, same parser as live ingest, so train/serve parity by construction).

## Schedules

### A. BigQuery only, spine first (full months follow, newest first)

17 calendar months, finishing 2028-02.

| calendar month | GB scanned | work |
|---|---:|---|
| 2026-10 | 844 | spine trusted (125 mo: 2015-01..2025-05); spine degraded (1 mo: 2026-09) |
| 2026-11 | 634 | spine degraded (15 mo: 2025-06..2026-08); full trusted (1 mo: 2025-05) |
| 2026-12 | 509 | full trusted (1 mo: 2025-04) |
| 2027-01 | 523 | full trusted (1 mo: 2025-03) |
| 2027-02 | 464 | full trusted (1 mo: 2025-02) |
| 2027-03 | 467 | full trusted (1 mo: 2025-01) |
| 2027-04 | 449 | full trusted (1 mo: 2024-12) |
| 2027-05 | 612 | full trusted (1 mo: 2024-11) |
| 2027-06 | 769 | full trusted (2 mo: 2024-09..2024-10) |
| 2027-07 | 883 | full trusted (2 mo: 2024-07..2024-08) |
| 2027-08 | 876 | full trusted (2 mo: 2024-05..2024-06) |
| 2027-09 | 464 | full trusted (1 mo: 2024-04) |
| 2027-10 | 874 | full trusted (2 mo: 2024-02..2024-03) |
| 2027-11 | 793 | full trusted (2 mo: 2023-12..2024-01) |
| 2027-12 | 850 | full trusted (2 mo: 2023-10..2023-11) |
| 2028-01 | 757 | full trusted (2 mo: 2023-08..2023-09) |
| 2028-02 | 749 | full trusted (2 mo: 2023-06..2023-07) |

### B. BigQuery only, detail first (original Phase 2 priority)

17 calendar months; the 2015-2023 spine would not exist until 2028-02, so no modelling could start. Not recommended.

| calendar month | GB scanned | work |
|---|---:|---|
| 2026-10 | 485 | full trusted (1 mo: 2025-05) |
| 2026-11 | 509 | full trusted (1 mo: 2025-04) |
| 2026-12 | 523 | full trusted (1 mo: 2025-03) |
| 2027-01 | 464 | full trusted (1 mo: 2025-02) |
| 2027-02 | 467 | full trusted (1 mo: 2025-01) |
| 2027-03 | 449 | full trusted (1 mo: 2024-12) |
| 2027-04 | 612 | full trusted (1 mo: 2024-11) |
| 2027-05 | 769 | full trusted (2 mo: 2024-09..2024-10) |
| 2027-06 | 883 | full trusted (2 mo: 2024-07..2024-08) |
| 2027-07 | 876 | full trusted (2 mo: 2024-05..2024-06) |
| 2027-08 | 464 | full trusted (1 mo: 2024-04) |
| 2027-09 | 874 | full trusted (2 mo: 2024-02..2024-03) |
| 2027-10 | 793 | full trusted (2 mo: 2023-12..2024-01) |
| 2027-11 | 850 | full trusted (2 mo: 2023-10..2023-11) |
| 2027-12 | 757 | full trusted (2 mo: 2023-08..2023-09) |
| 2028-01 | 894 | full trusted (2 mo: 2023-06..2023-07); spine trusted (14 mo: 2022-04..2023-05) |
| 2028-02 | 528 | spine trusted (87 mo: 2015-01..2022-03); spine degraded (16 mo: 2025-06..2026-09) |

### C. Recommended hybrid: BigQuery for spine, hourly files for detail

1. BigQuery spine for every month: 994 GB over 2 calendar months (2026-10, 2026-11); trusted months first, newest to oldest, degraded months last.
2. Detail columns for the 24 trusted months (2023-06..2025-05) from hourly files on the laptop (`breakout backfill hourly-detail`, the optional Phase 2 deliverable 7), newest month first, <= 4 concurrent downloads. This costs bandwidth and local CPU only.
3. One BigQuery full-mode day (about 15 GB) for the parity check (`breakout backfill parity`), inside the same quota month as step 1.
4. `detail_start_date` becomes 2023-06 when step 2 completes, and moves month by month as it progresses (Tier B features are NaN before it).

## Per-year totals (GB scanned)

| year | spine | full | push (stand-alone) |
|---|---:|---:|---:|
| 2015 | 18 | 485 | 13 |
| 2016 | 28 | 755 | 20 |
| 2017 | 36 | 974 | 26 |
| 2018 | 43 | 1,167 | 30 |
| 2019 | 55 | 1,752 | 39 |
| 2020 | 80 | 3,124 | 56 |
| 2021 | 89 | 3,692 | 62 |
| 2022 | 119 | 5,191 | 82 |
| 2023 | 133 | 4,810 | 92 |
| 2024 | 168 | 5,351 | 115 |
| 2025 | 146 | 4,369 | 100 |
| 2026 | 79 | 613 | 55 |
| **total** | **994** | **32,282** | **687** |

## Per-month bytes (GB scanned)

| month | era | spine | full | push | full/spine |
|---|---|---:|---:|---:|---:|
| 2015-01 | trusted | 1.2 | 31.6 | 0.8 | 26 |
| 2015-02 | trusted | 1.3 | 33.3 | 0.9 | 27 |
| 2015-03 | trusted | 1.5 | 39.2 | 1.1 | 26 |
| 2015-04 | trusted | 1.5 | 37.9 | 1.0 | 26 |
| 2015-05 | trusted | 1.5 | 37.7 | 1.0 | 25 |
| 2015-06 | trusted | 1.5 | 39.0 | 1.0 | 27 |
| 2015-07 | trusted | 1.5 | 40.6 | 1.1 | 27 |
| 2015-08 | trusted | 1.5 | 40.4 | 1.1 | 27 |
| 2015-09 | trusted | 1.6 | 43.2 | 1.1 | 27 |
| 2015-10 | trusted | 1.8 | 48.0 | 1.2 | 27 |
| 2015-11 | trusted | 1.8 | 49.6 | 1.3 | 27 |
| 2015-12 | trusted | 1.7 | 44.8 | 1.2 | 26 |
| 2016-01 | trusted | 2.0 | 51.6 | 1.4 | 26 |
| 2016-02 | trusted | 2.1 | 56.2 | 1.5 | 26 |
| 2016-03 | trusted | 2.4 | 64.3 | 1.7 | 26 |
| 2016-04 | trusted | 2.4 | 64.2 | 1.7 | 27 |
| 2016-05 | trusted | 2.4 | 65.2 | 1.7 | 27 |
| 2016-06 | trusted | 2.2 | 59.5 | 1.5 | 27 |
| 2016-07 | trusted | 2.2 | 59.8 | 1.5 | 27 |
| 2016-08 | trusted | 2.4 | 66.2 | 1.7 | 28 |
| 2016-09 | trusted | 2.4 | 66.4 | 1.7 | 27 |
| 2016-10 | trusted | 2.6 | 68.4 | 1.8 | 27 |
| 2016-11 | trusted | 2.6 | 69.4 | 1.8 | 27 |
| 2016-12 | trusted | 2.4 | 63.3 | 1.7 | 26 |
| 2017-01 | trusted | 2.5 | 70.6 | 1.8 | 28 |
| 2017-02 | trusted | 2.7 | 73.1 | 1.9 | 27 |
| 2017-03 | trusted | 3.2 | 86.0 | 2.3 | 27 |
| 2017-04 | trusted | 2.9 | 77.3 | 2.1 | 26 |
| 2017-05 | trusted | 3.0 | 81.4 | 2.1 | 27 |
| 2017-06 | trusted | 2.9 | 78.9 | 2.0 | 27 |
| 2017-07 | trusted | 2.9 | 77.5 | 2.0 | 27 |
| 2017-08 | trusted | 3.0 | 81.8 | 2.1 | 27 |
| 2017-09 | trusted | 3.0 | 80.1 | 2.1 | 26 |
| 2017-10 | trusted | 3.4 | 94.0 | 2.4 | 28 |
| 2017-11 | trusted | 3.5 | 92.0 | 2.5 | 26 |
| 2017-12 | trusted | 3.2 | 80.8 | 2.3 | 25 |
| 2018-01 | trusted | 3.6 | 92.9 | 2.5 | 26 |
| 2018-02 | trusted | 3.4 | 89.1 | 2.4 | 26 |
| 2018-03 | trusted | 4.0 | 103.5 | 2.8 | 26 |
| 2018-04 | trusted | 3.7 | 91.3 | 2.6 | 25 |
| 2018-05 | trusted | 3.5 | 93.3 | 2.5 | 27 |
| 2018-06 | trusted | 3.4 | 96.3 | 2.4 | 28 |
| 2018-07 | trusted | 3.4 | 95.2 | 2.4 | 28 |
| 2018-08 | trusted | 3.4 | 98.0 | 2.4 | 29 |
| 2018-09 | trusted | 3.3 | 93.1 | 2.4 | 28 |
| 2018-10 | trusted | 3.9 | 117.0 | 2.7 | 30 |
| 2018-11 | trusted | 3.7 | 106.2 | 2.6 | 29 |
| 2018-12 | trusted | 3.4 | 91.1 | 2.4 | 27 |
| 2019-01 | trusted | 3.7 | 105.7 | 2.6 | 29 |
| 2019-02 | trusted | 4.0 | 118.4 | 2.8 | 30 |
| 2019-03 | trusted | 4.6 | 137.5 | 3.3 | 30 |
| 2019-04 | trusted | 4.6 | 134.6 | 3.2 | 30 |
| 2019-05 | trusted | 4.6 | 139.0 | 3.2 | 31 |
| 2019-06 | trusted | 4.2 | 133.8 | 3.0 | 32 |
| 2019-07 | trusted | 4.7 | 150.8 | 3.3 | 32 |
| 2019-08 | trusted | 4.6 | 143.7 | 3.2 | 31 |
| 2019-09 | trusted | 4.6 | 143.4 | 3.2 | 31 |
| 2019-10 | trusted | 5.3 | 188.5 | 3.7 | 36 |
| 2019-11 | trusted | 5.1 | 180.5 | 3.6 | 35 |
| 2019-12 | trusted | 4.9 | 176.4 | 3.4 | 36 |
| 2020-01 | trusted | 5.1 | 175.3 | 3.5 | 35 |
| 2020-02 | trusted | 5.3 | 191.1 | 3.7 | 36 |
| 2020-03 | trusted | 6.4 | 238.8 | 4.4 | 37 |
| 2020-04 | trusted | 6.9 | 252.9 | 4.8 | 37 |
| 2020-05 | trusted | 6.8 | 230.7 | 4.7 | 34 |
| 2020-06 | trusted | 6.6 | 265.2 | 4.6 | 40 |
| 2020-07 | trusted | 7.1 | 303.3 | 4.9 | 43 |
| 2020-08 | trusted | 6.1 | 233.2 | 4.3 | 38 |
| 2020-09 | trusted | 7.5 | 341.1 | 5.2 | 45 |
| 2020-10 | trusted | 7.7 | 315.5 | 5.4 | 41 |
| 2020-11 | trusted | 7.2 | 278.6 | 5.0 | 39 |
| 2020-12 | trusted | 7.3 | 298.7 | 5.1 | 41 |
| 2021-01 | trusted | 7.3 | 302.8 | 5.1 | 41 |
| 2021-02 | trusted | 6.9 | 282.5 | 4.8 | 41 |
| 2021-03 | trusted | 8.1 | 361.1 | 5.6 | 45 |
| 2021-04 | trusted | 7.9 | 326.8 | 5.5 | 42 |
| 2021-05 | trusted | 7.4 | 350.5 | 5.1 | 47 |
| 2021-06 | trusted | 8.0 | 352.5 | 5.6 | 44 |
| 2021-07 | trusted | 7.7 | 306.6 | 5.3 | 40 |
| 2021-08 | trusted | 7.7 | 328.6 | 5.3 | 43 |
| 2021-09 | trusted | 8.0 | 328.9 | 5.5 | 41 |
| 2021-10 | trusted | 3.4 | 120.2 | 2.4 | 35 |
| 2021-11 | trusted | 8.3 | 321.9 | 5.8 | 39 |
| 2021-12 | trusted | 8.5 | 309.8 | 5.9 | 37 |
| 2022-01 | trusted | 9.1 | 383.3 | 6.3 | 42 |
| 2022-02 | trusted | 10.0 | 554.5 | 6.9 | 56 |
| 2022-03 | trusted | 9.5 | 410.2 | 6.5 | 43 |
| 2022-04 | trusted | 9.2 | 397.1 | 6.3 | 43 |
| 2022-05 | trusted | 8.9 | 366.1 | 6.2 | 41 |
| 2022-06 | trusted | 8.9 | 396.7 | 6.1 | 45 |
| 2022-07 | trusted | 9.3 | 380.9 | 6.4 | 41 |
| 2022-08 | trusted | 10.0 | 397.7 | 6.9 | 40 |
| 2022-09 | trusted | 10.4 | 395.9 | 7.2 | 38 |
| 2022-10 | trusted | 11.7 | 477.2 | 8.1 | 41 |
| 2022-11 | trusted | 10.8 | 477.1 | 7.5 | 44 |
| 2022-12 | trusted | 11.2 | 554.7 | 7.7 | 50 |
| 2023-01 | trusted | 11.3 | 482.3 | 7.8 | 43 |
| 2023-02 | trusted | 10.3 | 400.8 | 7.1 | 39 |
| 2023-03 | trusted | 11.6 | 435.8 | 8.0 | 38 |
| 2023-04 | trusted | 10.4 | 380.1 | 7.2 | 36 |
| 2023-05 | trusted | 10.5 | 386.0 | 7.2 | 37 |
| 2023-06 | trusted | 10.1 | 365.1 | 7.0 | 36 |
| 2023-07 | trusted | 10.4 | 384.0 | 7.2 | 37 |
| 2023-08 | trusted | 10.7 | 380.5 | 7.4 | 35 |
| 2023-09 | trusted | 10.7 | 376.3 | 7.3 | 35 |
| 2023-10 | trusted | 11.5 | 433.1 | 7.9 | 38 |
| 2023-11 | trusted | 12.2 | 417.0 | 8.4 | 34 |
| 2023-12 | trusted | 13.6 | 368.7 | 9.3 | 27 |
| 2024-01 | trusted | 13.5 | 424.6 | 9.2 | 32 |
| 2024-02 | trusted | 15.1 | 427.0 | 10.2 | 28 |
| 2024-03 | trusted | 14.6 | 446.9 | 10.0 | 31 |
| 2024-04 | trusted | 14.7 | 464.2 | 10.0 | 32 |
| 2024-05 | trusted | 14.0 | 449.4 | 9.6 | 32 |
| 2024-06 | trusted | 13.0 | 427.0 | 8.9 | 33 |
| 2024-07 | trusted | 13.2 | 448.6 | 9.0 | 34 |
| 2024-08 | trusted | 13.2 | 434.5 | 9.0 | 33 |
| 2024-09 | trusted | 13.3 | 409.6 | 9.1 | 31 |
| 2024-10 | trusted | 14.7 | 358.9 | 10.1 | 24 |
| 2024-11 | trusted | 14.7 | 611.5 | 10.0 | 42 |
| 2024-12 | trusted | 13.6 | 448.5 | 9.3 | 33 |
| 2025-01 | trusted | 14.7 | 466.5 | 10.1 | 32 |
| 2025-02 | trusted | 14.3 | 463.5 | 9.8 | 32 |
| 2025-03 | trusted | 16.1 | 522.9 | 11.1 | 32 |
| 2025-04 | trusted | 15.4 | 508.8 | 10.6 | 33 |
| 2025-05 | trusted | 14.2 | 485.0 | 9.8 | 34 |
| 2025-06 | degraded | 10.2 | 375.5 | 7.0 | 37 |
| 2025-07 | degraded | 10.7 | 385.0 | 7.4 | 36 |
| 2025-08 | degraded | 10.7 | 396.7 | 7.4 | 37 |
| 2025-09 | degraded | 10.6 | 388.4 | 7.3 | 37 |
| 2025-10 | degraded | 8.4 | 161.6 | 5.8 | 19 |
| 2025-11 | degraded | 9.9 | 104.1 | 6.9 | 11 |
| 2025-12 | degraded | 10.2 | 110.6 | 7.1 | 11 |
| 2026-01 | degraded | 10.1 | 111.4 | 7.0 | 11 |
| 2026-02 | degraded | 9.1 | 102.2 | 6.3 | 11 |
| 2026-03 | degraded | 10.7 | 109.8 | 7.4 | 10 |
| 2026-04 | degraded | 10.1 | 101.2 | 7.0 | 10 |
| 2026-05 | degraded | 10.4 | 66.2 | 7.2 | 6 |
| 2026-06 | degraded | 10.2 | 41.3 | 7.0 | 4 |
| 2026-07 | degraded | 10.5 | 36.0 | 7.2 | 3 |
| 2026-08 | degraded | 7.4 | 27.2 | 5.1 | 4 |
| 2026-09 | degraded | 0.4 | 17.4 | 0.3 | 43 |

## Decisions needed (HUMAN DECISION in Phase 2)

1. `history.cutover_date`: proposed **2026-09-06** (first day of the OpenDigger-era hourly feed). The BigQuery backfill then covers `[2015-01-01, cutover)`; the Phase 2 default (first day of the current month) would leave 2026-09-06..2026-09-30 to be re-ingested twice.
2. Approve schedule C (recommended), A, or B.
3. Degraded months (2025-06..2026-09-05) are spine-only in every schedule; they are kept for context and for live-scoring look-back windows, never for training/evaluation.
