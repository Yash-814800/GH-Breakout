# Progress

Update this file at the end of every phase: tick the box, add the date, and record numbers you
measured (row counts, sizes, runtimes, metrics). Future sessions rely on it.

| Phase | Title | Status | Date | Notes |
|---|---|---|---|---|
| 00 | Bootstrap & guardrails | ☑ | 2026-10-12 | 26 tests pass; ruff, mypy, pre-commit (incl. gitleaks) green locally. CI green on GitHub (run 38189757833). |
| 01 | Schema audit, slim schema, hourly parser | ☑ | 2026-10-12 | 9 eras audited; day 2026-10-10 ingested: 24/24 hours ok, 763,462 rows, 39 s wall clock, 12 MB lake + 24 MB staging; rerun no-op (0.5 s, files checksum-identical). See open issue on star volume. |
| 02 | BigQuery cost plan & historical backfill | ☑ | 2026-10-13 | Spine 2015-01..2023-05 complete: 498/498 units, 101/101 months finalized, 0 failed, 522.7 GB billed, 57 GB lake (3.26 G events). Re-run performs 0 queries; `lake verify` OK (963 files). Parity PASS (2024-06-03, 2026-10-10). Hourly era from 2023-06-01 runs in Actions (ADR-011). Lake lives on the Lexar SSD, symlinked from `data/lake` (ADR-012). |
| 03 | Lake on Hugging Face (layout, upload, sync, compaction) | ☑ | 2026-10-15 | 4 public repos; 943 files, 60.68 GB, 3.26 G rows on the Hub (44 commits); catalog + cards live; pull and `hf://` queries verified; `lake verify --remote` 0 problems; 163 tests pass. Hourly-era backfill done 2026-10-16: 1,523 files, 114.91 GB, 5.59 G rows, 142 months, 41/41 jobs ok, 2 hours missing upstream. |
| 04 | Enrichment (repo metadata, actor age, trending, HN) | ☑ | 2026-10-16 | 7 tables built and on the Hub (`derived/enrich/`): name history 46.5 M pairs, metadata 1,684,571 repos (76.5% found / 23.5% not_found), actor-age map median error 1.9 days, trending 1.52 M rows over 4,360 days, HN 196,217 stories; 226 tests pass. See "Phase 4 status" and ADR-016..019. |
| 05 | dbt staging & intermediate models | ☑ | 2026-10-19 | 35 models (17 staging, 18 intermediate; 5 are new prefilters or moved, ADR-020), 162 tests, all pass on the full trusted history 2015-01-01..2025-05-23: warehouse 33 GB, 4.3 G source events. Built with hash-bucketed incremental models (ADR-020). 236 pytest pass. See "Phase 5 status". |
| 06 | Candidates, labels, baseline, evaluation harness | ☑ | 2026-10-19 | **Corrected 2026-10-19 (ADR-024)**: repos with unknown metadata were silently dropped by a NULL in the bot-owner filter. 3 marts, 33 dbt tests pass; 486 matured snapshots, **3,098,574** candidate rows (was 2,485,109), 0.509% positive; B1 pooled PR-AUC **0.0286** [0.0246, 0.0345] (was 0.0520), P@25 0.109; 29 folds. See "Phase 6 status".
| 07 | Point-in-time feature marts | ☑ | 2026-10-19 | 7 feature groups + mart, 71 features (68 live-available), 63 dbt tests pass; 3,098,574 training rows 2016-2025; leak test PASS on 2018-05-14, 2021-03-01, 2024-06-03 and 2026-10-12 (300 repos x 71 columns each); live build for 2026-10-15 has identical columns/types; 17 tests in tests/features. See "Phase 7 status" and ADR-022..024.
| 08 | LightGBM, calibration, SHAP, model registry | ☑ (HF upload pending approval) | 2026-10-19 | Model beats B1 in all 29 folds: pooled PR-AUC **0.108** [0.101, 0.113] vs 0.029, P@25 **0.241** [0.229, 0.255] vs 0.109; holdout (26 weeks to 2025-04-21) 0.158 / 0.338 vs B1 0.032 / 0.106. Sanity checks pass; calibrated ECE 0.0002. Champion `20261019-b5ff585` (local registry). Daily check: calibration over-predicts on non-Mondays (ADR-025). 310 tests pass. See "Phase 8 status". |
| 09 | Daily pipeline, weekly retrain, health checks | ☑ | 2026-10-20 | 5 GitHub Actions workflows (`daily.yml`, `weekly.yml`, `monthly.yml`, `health.yml`, `backfill-day.yml`). Persistent state as of 2023-06-01 on HF (`tastemaker_state`, `owner_state`, `tastemaker_thresholds`). Parity test PASS (2024-06-03, Jaccard 1.0000, cell match 99.99%, Spearman 0.9999). SHA-256 tamper-evident ledger, PSI drift monitoring, ops runbook. 328 tests pass. See "Phase 9 status". |
| 10 | Website (Astro) + deploy | ☐ | | |
| 11 | Fake-star detector, similar repos, cohort retention | ☐ | | |
| 12 | Distribution (RSS, badges, digest, Bluesky) | ☐ | | |
| 13 | Portfolio polish, dbt docs, ClickHouse benchmark, final audit | ☐ | | |

## Amendments after Phase 1 (ADR-009, ADR-010, 2026-10-12)

| Item | Status | Notes |
|---|---|---|
| `GH_ENRICH_TOKEN` classic no-scope PAT, 1-year expiry | ☑ set locally; ☑ Actions secret | verified (5,000 req/h, no scopes). Rotation reminder in `docs/runbook.md` (expires 2027-10-12) |
| `history.trusted_end = 2025-05-23`, `latest_trusted_snapshot` 2025-04-24 | ☑ | `degraded_end` removed; degraded era runs to `live.source_start` (null) |
| `history.cutover_date = 2023-06-01`, `detail_start_date = 2023-06-01`, `hourly_gap_days` | ☑ | |
| `live.source` / `live.source_start` | ☑ keys, both null | switch gated on source test + human approval |
| BigQuery spine 2015-01..2023-05 | ☑ done 2026-10-13 | 522.7 GB billed, 101/101 months, 57 GB lake (ADR-012) |
| `breakout backfill hourly` (trusted first, <= 4 downloads, resumable) | ☑ code, ☐ run | ~2 TB download (trusted ~1.5 TB, degraded ~0.5 TB). **Not to be run on the laptop (ADR-011): Actions matrix in Phase 3** |
| `breakout lake verify` + invariants | ☑ | ADR-010 |
| `live_available` in `config/feature_dictionary.yaml` + validator | ☑ | entries arrive in Phase 7; the file already validates |
| Provisional-window logic (`Config.window_is_provisional`) | ☑ | leaderboard flag + methodology wording land with Phase 7/10 |
| Capture-quality report re-rendered for `trusted_end` 2025-05-23 | ☑ | `reports/capture_quality.md` |
| Source test from a GitHub Actions runner | ☑ NO-GO | OpenDigger ~0.01 MB/s from the runner (needs >= 1), manifests 404; gharchive 54 MB/s. `reports/source_validation.md`, run 38194688025 |
| Stargazers API for per-repo ground truth | ✖ not available | GitHub restricted it to admins/collaborators in July 2026 (ADR-010) |
| Live-source gate / item 5 | ☐ not started | waits for your review of the source test |

## Phase 9 status (2026-10-20)

- **Code:**
  - Workflows: `.github/workflows/{daily,weekly,monthly,health,backfill-day}.yml`
  - Persistent state: `src/breakout/features/state.py` (`build_state`, `update_state`, `sync_state_hf`)
  - dbt persistent state integration: `feat_tastemaker.sql` & `feat_owner.sql` (`use_persistent_state` branch)
  - Daily orchestrator: `src/breakout/daily/run.py` (15-step sequential runner)
  - Ops tooling: `src/breakout/ops/{ledger,drift,parity}.py`
  - Publish exporter: `src/breakout/publish/site_data.py` (`export_leaderboard`, `export_status`)
  - ML live append & promotion: `src/breakout/ml/append_live.py`, `src/breakout/ml/final.py` (`evaluate_and_promote`)
  - CLI commands: `breakout daily run`, `breakout ops {verify-ledger,drift,parity}`, `breakout publish site-data`, `breakout ml append-live`, `breakout build state`.
- **Training/Serving Parity (§9.6):**
  - Evaluated on snapshot `2024-06-03` against history warehouse mart.
  - Candidate Jaccard: **1.0000** (12,434 / 12,434, required >= 0.99) -> **PASS**
  - Overall cell match rate: **99.99%** (required >= 0.99) -> **PASS**
  - Prediction rank correlation (Spearman rho): **0.9999** (required >= 0.99) -> **PASS**
  - 100% of feature columns met parity thresholds (0 discrepancies). Report: `docs/parity_daily_vs_history.md`.
- **Tamper-Evident Ledger:**
  - SHA-256 hash chaining implemented with genesis hash `0000000000000000000000000000000000000000000000000000000000000000`.
  - Integrity verified with `breakout ops verify-ledger`.
- **Feature Drift Monitoring:**
  - Population Stability Index (PSI) implemented for numerical and categorical features across 14 key features.
  - Output report written to `reports/drift_report.json`.
- **Operational Runbook:**
  - `docs/runbook.md` updated with daily operations, manual day backfills, rollback procedures, and alert runbooks.
- **Verification:**
  - 328 passing tests (`pytest -q`).
  - Linter and formatter: `ruff check .` (0 errors), `ruff format --check .` (clean).
  - Type checker: `mypy src` (0 errors across 73 source files).
  - ADR-026 recorded in `docs/DECISIONS.md`.

## Phase 8 status (2026-10-19)

- Code: `breakout.ml.{dataset,train,calibrate,cv,cv_report,explain,final,registry,card,daily_check}`; CLI `breakout ml cv [--variant V]
  [--fold N] [--report]`, `train-final`, `predict --date D`, `explain --version V`, `daily-check`; config section `model:`; dbt
  `mart_snapshot_dates` `range` mode; `features.build.run_features_range`; 35 new tests in `tests/ml/test_model.py`. Design: ADR-025.
- **CV** (29 folds, test snapshots 2018-02..2025-05, 2,667,524 rows, 13,558 positives): model PR-AUC 0.1081 [0.1013, 0.1134],
  ROC-AUC 0.883, P@10 0.340, P@25 0.241, P@50 0.176; B1 0.0286 / 0.816 / 0.129 / 0.109 / 0.086. Paired difference vs B1: PR-AUC
  +0.079 [+0.070, +0.088], P@25 +0.132 [+0.116, +0.149]. P@25 by year (model / B1): 2018 .195/.102, 2019 .181/.116, 2020 .219/.132,
  2021 .207/.123, 2022 .252/.143, 2023 .291/.085, 2024 .306/.055, 2025 .350/.133. Lead time vs Trending (top-25): flagged before
  Trending 22.2% (B1 8.8%), never flagged 62.8% (B1 80.1%), median lead 1 d.
- **Ablations** (3 configs/fold, vs all features): Tier A only +0.006 PR-AUC [-0.001, +0.015]; A+B -0.003; no tastemaker -0.001;
  no stargazer group -0.003; star-dynamics group only -0.043 [-0.054, -0.030]. Tier B / C add no measurable lift. Monotone constraints:
  -0.001 PR-AUC, not kept.
- **Sanity:** labels permuted within snapshot -> PR-AUC 0.0058 vs rate 0.0051 (PASS); `stars_7d`-only model 0.0290 / P@25 0.104 vs B1 0.0286 / 0.109.
- **Calibration:** isotonic in all 29 folds; pooled OOF ECE 0.00022, Brier 0.00471 (raw score ECE 0.042: negatives are subsampled to 10%).
- **Final model** `20261019-b5ff585` (`data/models/`, not yet on the Hub): trained 2021-04..2025-04 (last 3 months validate + calibrate),
  holdout 2024-10-28..2025-04-21 via the evaluation model: PR-AUC 0.1578 vs B1 0.0323, P@25 0.338 vs 0.106, ECE raw 0.0366 -> 0.0009. Promoted
  (first model must beat B1). `breakout ml predict --date 2026-10-15` prints top 10 with probabilities and sentences (the lake ends
  2026-10-14, so the newest live features are 2026-10-15; they sit after the 2025-05 capture collapse, so those probabilities are not meaningful yet).
- **Daily vs weekly:** see ADR-025 addendum; non-Monday calibration observed/expected 0.73 vs 0.90 on Mondays.
- Runtimes (1 thread, 4 GB cap): `full` CV ~1 h 10, each 3-config ablation ~25 min, `train-final` ~4 min, daily range build ~35 min on a warehouse copy (deleted).
- Figures: `reports/figures/{cv_pr_curve,cv_precision_by_year,cv_reliability,shap_importance,shap_beeswarm}.png`.

## Phase 7 status (2026-10-19)

- Code: dbt `models/features/{feat_star_dynamics,feat_activity,feat_stargazers,feat_tastemaker,feat_owner,feat_detail,
  feat_enrich,mart_repo_features}` + `_features.yml`, intermediates `int_actor_early_stars`, `int_actor_early_cum`,
  `int_repo_first_hit`, `int_tastemaker_thresholds`, macro `shannon_entropy_bits`, seed `top_languages` (30 languages),
  5 singular tests (`features_no_future_inputs`, `features_star_windows_match_candidates`,
  `features_tier_b_null_before_detail`, `features_row_parity`, `features_stg_stars_bucket_layout`) and
  `candidates_keep_unknown_metadata`; Python `breakout.features.{build,leak,eda,publish}`; CLI `breakout build
  features --history | --date D`, `build leak-test`, `build feature-eda`; `config/feature_dictionary.yaml` (71 entries);
  `int_repo_daily_activity` gained `n_comment_events`, `n_pr_events` (rebuilt, 138,886,100 rows unchanged).
  Tests: `tests/features/` (17: hand-computed synthetic world + leak machinery + export/EDA helpers), dictionary and CLI tests.
- **How to run:** same env/caps as Phase 5 (local `GHB_WAREHOUSE`), from a frozen copy of `dbt/` (`GHB_DBT_DIR`, runbook), then
  `breakout build features --history` (resumable by bucket; runs the dbt tests and exports the training table).
- **Build time** (single thread, 2 GB, 32 buckets, sum of the dbt-reported model times; dbt start-up adds ~12 s per call):
  `int_actor_early_stars` 176 s, `int_actor_early_cum` 40 s, `int_tastemaker_thresholds` 18 s; `feat_activity` 439 s,
  `feat_stargazers` 342 s, `feat_owner` 315 s, `feat_tastemaker` 235 s, `feat_detail` 125 s, `feat_star_dynamics` 105 s,
  `feat_enrich` 11 s, `mart_repo_features` 122 s. The history build is ~12 min (intermediates) + ~31 min (groups) of wall clock.
  Peak model memory measured on real data (one bucket): 1.1-1.6 GB RSS with the 2 GB DuckDB limit.
- **Rows:** `mart_repo_features` 3,146,887 rows (4 unmatured snapshots included); training table (matured snapshots only)
  3,098,574 rows, 71 features + 7 label columns, `data/derived/training/features_labels/year=2016..2025/part-0.parquet`
  (139 MB), `feature_manifest.json`. Per year: 190,364 / 217,516 / 235,103 / 262,977 / 311,582 / 279,747 / 341,416 /
  547,801 / 513,712 / 198,356 (2016..2025).
- **Tastemaker:** 43,137,077 early stars with an observable outcome, hit rate 4.85% (8.5% in 2015, 3.0% in 2023); 5,568,720
  actors, 29,067,175 (actor, outcome-day) states, 18,514,068 with >= 5 known early stars; beta = 20 (ADR-022).
- **NULL rates** (`reports/metrics/feature_null_rates.json`, `reports/feature_eda.md`): Tier B features are 100% NULL up to
  2022 and 44% in 2023 (detail starts 2023-06-01), 0% from 2024 for the count features and 72-85% for the ratio / median
  ones (no issue or PR in the window). Tier A with sparse support: `days_since_last_release` 81-87% (no release),
  `median_session_minutes_28d` / `top_actor_share_28d` / `first_time_contributor_rate_28d` 45-65% (no contribution
  session), `sg_retention_*` 19-29%, `star_max_hour_share_7d` 10-23%, `hn_max_points_aged` 95-99%.
- **Leak test** (`breakout build leak-test`, 300 sampled candidates, 71 columns, full world vs inputs truncated at D):
  `2018-05-14 PASS (60 columns have non-NULL values; the 11 Tier B columns are NULL before 2023)`, `2021-03-01 PASS (first of
  a month: threshold boundary M == D)`, `2024-06-03 PASS (71/71)`, `2026-10-12 PASS (after the 2025-10-07 payload trim, on a
  window warehouse, 68/71)`; each also reproduces the real mart rows exactly (0 differing). Mutation check: `>=` instead of `>`
  on the outcome day or `<=` instead of `<` on the star day make the synthetic leak test fail.
- **Live build:** window warehouse 2026-05-01..2026-10-14 built with the daily-run shape (no buckets): 34 dbt models in 3 min,
  `lake pull` of that window 4.0 GB / 190 files; `breakout build features --date 2026-10-15` (the newest possible date: the lake
  ends 2026-10-14) gives 1,253 candidates and `data/derived/live/features_2026-10-15.parquet` with the **same 74 columns,
  order and types** as the training table. 2026-10-12: 1,396 candidates. Metadata of these repos is not fetched yet (Phase 9).
- **EDA:** top univariate ROC-AUCs `stars_3d` 0.817, `stars_7d` 0.811, `actor_days_14d` 0.784, `stars_1d` 0.779,
  `sg_tm_max_14d` 0.779 (tastemaker), `sg_n` 0.774; `star_max_hour_share_7d` 0.241 (a one-hour burst points away from a breakout).
  11 correlation clusters at |rho| >= 0.8 (e.g. `stars_14d`/`sg_n`/`actor_days_14d`).
- Hugging Face: `training/` is on the derived repo (11 files, 145 MB, one commit; a second upload run is a no-op). The
  manifest records dbt git sha `3ee9068` and the dictionary sha256 (`49d9891c...`). `labels/candidates_labels.parquet` on the
  Hub was re-uploaded with the corrected file (41.9 MB, 1 commit) with the human's approval.
- Warehouse: the finished local build copy (`~/.cache/ghb-warehouse/`) was copied to `data/warehouse.duckdb` on the SSD
  (byte-identical check); the superseded Phase 6 file was deleted with the human's approval.

## Phase 6 status (2026-10-19)

- **Correction (ADR-024):** the numbers below were measured before a NULL-semantics bug was found (repos with unknown
  metadata were dropped from `mart_candidates`). After the fix: 3 marts, 33 dbt tests pass; 486 matured snapshots, **3,098,574**
  candidate-label rows, 1,125,113 distinct repos, 9,606 distinct positive repos, median 5,626.5 candidates per snapshot,
  0.509% positive; rows per year 2016..2025: 190k, 218k, 235k, 263k, 312k, 280k, 341k, 548k, 514k, 198k; positives:
  981, 1117, 1204, 1348, 1585, 1418, 1734, 2778, 2605, 1003 (`breakout_abs`: 638, 739, 644, 600, 645, 519, 554, 980,
  820, 393). B1 pooled PR-AUC 0.0286 [0.0246, 0.0345], ROC-AUC 0.816, P@10 0.129, P@25 0.109 [0.100, 0.118], P@50 0.086;
  B2 0.0197 / 0.098; B3 0.0227 / 0.105. B1 P@25 by year: 2018 .102, 2019 .116, 2020 .132, 2021 .123, 2022 .143, 2023 .085,
  2024 .055, 2025 .133. Lead time vs Trending (B1): 3,053 trending repos, 80.1% never flagged, 8.8% flagged before Trending.
  `mart_candidates` rebuilt in 293 s (32 buckets), `mart_labels` 20 s. The old figures are kept below for the record.
- Code: dbt `models/marts/{mart_snapshot_dates,mart_candidates,mart_labels}.sql` + `_marts.yml`, macro
  `latest_ingested_day`, singular tests `candidates_no_forks`, `labels_only_matured`, `labels_positive_rate`
  (warn), `candidates_known_repos`; Python `breakout.ml.{splits,metrics,baseline,labels_export}`; CLI
  `breakout build labels [--no-build] [--upload]` and `breakout ml baseline [--n-boot]`; `reports/baseline.md`,
  `reports/metrics/baseline.json`, two PNGs. Tests: 24 new `tests/ml` tests + CLI/config-var tests.
- **How to run:** same env/caps as Phase 5 (local warehouse), then `breakout build labels` (dbt marts, tests,
  export to `data/derived/labels/candidates_labels.parquet`, 33 MB) and `breakout ml baseline`.
- **Runtimes / memory:** `mart_candidates` 32 buckets x ~20 s, peak RSS 2.1 GB (4 GB cap, 2 GB DuckDB limit);
  `mart_labels` 20 s; snapshot dates <1 s; baseline report ~1.5 min with 1,000 bootstrap resamples.
- **Numbers:** 486 matured snapshots (490 total; the last four, 2025-04-28..05-19, are unmatured and have
  candidates but no labels); 2,485,109 candidate-label rows, 850,187 distinct repos, 7,759 distinct positive
  repos. Rows per year 2016..2025: 170k, 195k, 211k, 238k, 281k, 248k, 286k, 345k, 365k, 145k (to April).
  Positives per year: 882, 1001, 1079, 1220, 1433, 1266, 1457, 1754, 1856, 734. The floor (100 stars) never
  binds: the per-snapshot rate is the quantile's 0.5%. `breakout_abs` (>= 500 stars) is rarer: 378-948/year.
- The warehouse with the marts was copied to `data/warehouse.duckdb` on the SSD (byte-identical check) and the
  local build copy removed. `labels/candidates_labels.parquet` is on the derived Hub repo (1 commit, 33.7 MB).

## Phase 5 status (2026-10-19)

- Code: `dbt/` (35 models, 1 seed, 15 sources, 162 data tests; macros `lake_events`, `window_filter`, `bucket_col`;
  custom generic tests `no_rows_outside_window`, `monotonic_cumulative`, `birth_not_after_first_star`; singular
  tests for star sums, no duplicate stars, row counts), `src/breakout/dbt_runner.py`, CLI `breakout build dbt -- <args>` and
  `breakout build history [--start --end --buckets --resume-at a3 --no-test]`. `reports/phase5_spotcheck.md`
  has the 3-repo spot check (grok-1, screenshot-to-code, llm.c). `dbt docs generate` works (`dbt/target/catalog.json`).
- **How to run:** `GHB_WAREHOUSE=~/.cache/ghb-warehouse/warehouse.duckdb GHB_DUCKDB_TMP=~/.cache/ghb-duckdb-tmp
  GHB_DUCKDB_MAX_TEMP=10GB GHB_DUCKDB_MEMORY=2000MB systemd-inhibit --what=sleep:idle systemd-run --user --scope -p
  MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=100% uv run breakout build history` (resumable; background only). Keep
  the warehouse and the spill on the local disk while building, copy the result to `data/warehouse.duckdb`.
  Needs the lake pulled for 2023-06..2025-05 (all event types and push_daily; 62 -> 92 GB on the SSD).
- **Row counts** (full trusted history): stg_stars 476,598,600; int_repo_star_daily 246,821,950;
  int_star_active_repos 1,474,101; int_repo_birth 1,474,101; int_young_moving_repos 1,321,930 (89.7% of the
  star-active repos, so the stricter candidate filters of Phase 6 do the real selecting); int_active_repo_event_days
  183,503,814; int_bot_event_counts 15,957,085; int_repo_daily_activity 138,886,100; int_early_stars 72,671,090 =
  int_star_events_enriched 72,671,090; int_actor_daily_activity = int_actor_cumulative_activity 429,012,535;
  int_contributor_first_seen 26,311,258; int_contributor_sessions 155,390,270; int_core_actors_daily 45,864,602;
  int_issue_response 8,165,076; int_pr_lifecycle 9,855,887; int_stargazer_later_actions 17,077,485;
  int_star_cohort_retention 6,255,803; stg_bot_actors 59,586; stg_bot_actor_signals 910,182.
- **Runtimes** (single thread, 2 GB; seconds; bucketed = sum of buckets): stg_stars 1,998 (32); int_repo_star_daily
  134; int_star_active_repos 188; int_active_repo_event_days ~775; int_repo_birth ~98; int_bot_event_counts ~450;
  int_contributor_first_seen ~318; int_core_actors_daily ~688; int_actor_daily_activity ~25,000 (32 buckets; the
  slowest model, ~7 h); int_actor_cumulative_activity 429; int_star_events_enriched 1,198; int_repo_daily_activity
  7,880 (16); int_contributor_sessions 2,556 (16); int_stargazer_later_actions 3,326 (16); stg_bot_actor_signals
  ~1,850. A clean full build from scratch is roughly 15-20 h of wall clock; the daily window run is minutes.
- **Findings:** `birth_not_after_first_star` was 0.157% before the re-publication fix (ADR-020 item 6), 0 after.
  Three full-history attempts failed (OOM) and two DuckDB-on-NTFS stalls/I/O errors cost ~25 h before the design
  in ADR-020 (bucketing, local warehouse) was reached. Reviews exist only from 2020 (empty before).
- **For Phase 6:** `int_young_moving_repos` is only a superset; candidates still need `max_stars_total`,
  `exclude_forks`, `exclude_bot_owned` (use `int_repo_birth.is_fork/is_mirror_like` and `stg_repo_metadata`).
  Detail-dependent counts are NULL before 2023-06-01. `stg_stars` has a `bucket` column (repo_id % 32).

## Handoff to Phase 8 (state at 2026-10-19)

Start a fresh session with CLAUDE.md, this file, DECISIONS.md (ADR-020..024), ARCHITECTURE.md and `docs/phases/PHASE_08_*.md`.
- **Training table:** `data/derived/training/features_labels/year=YYYY/part-0.parquet` (also on the derived Hub repo under
  `training/`), 3,098,574 rows, the 71 features of `config/feature_dictionary.yaml` then the label columns (`breakout_rel`
  primary, `breakout_abs`, `gain_30d`, `threshold_rel`, ...) after `bucket, repo_id, snapshot_date`. `feature_manifest.json` lists
  features, live features (68), the dictionary hash and the dbt git sha. Read feature sets through
  `breakout.features_dict.model_features(feats, live_only=True)` (allowed AND live-available); `era_post_2025_10` is not allowed
  (constant 0 in training). Categoricals: `primary_language` (30 + Other + Unknown), `owner_type`.
- **Folds / baseline:** `breakout.ml.splits.make_folds` and `reports/baseline.md` (B1 pooled PR-AUC 0.0286, P@25 0.109 after the
  ADR-024 correction; B1 P@25 collapses to 0.085 / 0.055 in 2023 / 2024). A model has to beat these on PR-AUC and P@k.
- **Do not train the live champion on anything outside `live_available`**; the merge features (`prs_merged_28d`,
  `median_merge_hours_28d`) are research-only. Tier B features are NULL before 2023-06-01: LightGBM handles NaN, and
  `detail_coverage_28d` says how much of the window is covered.
- **Tastemaker** features use outcomes known before D only (strict `D > outcome_day`); do not add a feature that reads
  `gain_lookahead` or `is_hit` of a star whose `outcome_day >= D`. Any new feature must pass `breakout build leak-test`.
- **Live:** `breakout build features --date D` needs a warehouse with the daily window's staging / intermediate tables. The
  recipe used for the test: `breakout lake pull` the window (all raw types + `--push-daily`), then
  `dbt run --select staging intermediate` unbucketed with `events_start/end` (3 min for 5 months), then `build features --date`.
  Metadata (`primary_language`, `owner_type`, `days_api_created_to_birth`) is 'Unknown' / NULL for repos created after the trusted
  era until Phase 9 fetches it.
- `stg_stars.bucket` must be `repo_id % 32` (feature pruning, tested): build any window warehouse with the default 32 buckets.

## Handoff to Phase 5 (state at 2026-10-16; consumed by Phase 5)

Phase 5 (dbt staging and intermediate models) can start. Read `docs/DECISIONS.md` ADR-016..019 first.
- Enrichment tables are in `data/derived/enrich/` (SSD) and `Yasshh814/gh-breakout-derived` under `enrich/`:
  `repo_name_history`, `repo_targets`, `repo_metadata`, `actor_age_samples`, `actor_id_age_map`, `trending`,
  `hn_stories` (all `.parquet`). `hn_raw`/`hn_windows` (resume state) stay local.
- Local lake now also holds WatchEvent files for 2023-06..2026-10 (54 files, 4.6 GB, from the Hub). Other
  event types of the hourly era are still Hub-only: `lake pull --types ... --since 2023-06-01`.
- dbt sources: read the enrich parquet files; `ASOF_SQL` for the actor-age join and the
  `est_account_created_at()` helper live in `breakout.enrich.actor_age`; the `latest_names` view is
  `breakout.enrich.names.create_latest_names`.
- Metadata is **unknown** (not "false") for the 23.5% `not_found` repos; features from it must be NULL there.
- Daily jobs (Phase 9): `breakout enrich repos --repo-ids-file`, `trending-today`, `hn-recent --days 3`, and a
  monthly actor-age top-up (`actor-age --samples N`: the collector is incremental and the sample ids are
  deterministic, so a larger `--samples` fetches only the new ids). `enrich upload` is idempotent.
- `repo_targets` covers the trusted era only; Phase 9 must pass live candidates explicitly
  (`--repo-ids-file`).

## Phase 4 status (2026-10-16)

- Code: `src/breakout/enrich/` (`http, common, names, github_meta, actor_age, trending, hn, upload`), CLI group
  `breakout enrich names|targets|repos|actor-age|trending-history|trending-today|hn-history|hn-recent|upload`,
  config section `enrich:`, `enrichment_columns` allow-list in `config/feature_dictionary.yaml`. 226 tests pass
  (no live calls; fixtures `tests/fixtures/github_*.json`).
- Re-running every command is incremental: `repos` second run 0 requests (`skipped_fresh` 1,684,571),
  `hn-history` refetches 1 window (the open one), `trending-today` twice gives identical output, `upload` 2nd
  run 0 commits.
- **Name history:** 46,495,707 (repo_id, repo_name) pairs, 44,921,123 repos, 1.35 GB, built from WatchEvent
  spine columns 2015-01..2026-10-14 (ADR-016).
- **Repo metadata** (ADR-017): target set 1,684,571 repos (trusted era; >= 5 stars in a 14-day window starting
  within 120 days of the first star). Fetched all: **1,289,129 ok (76.5%)**, **395,442 not_found (23.5%)**,
  0 blocked, 0 error, 0 REST fallbacks, 0 id mismatches. About 16,900 GraphQL requests of 100 ids (cost 1
  each), ~95 repos/s with 5 concurrent batches under one 1 request/s throttle, ~4.5 h wall clock. Found share
  by first-star year: 2015 90.7%, 2016 87.5%, 2017 87.8%, 2018 88.0%, 2019 88.0%, 2020 83.4%, 2021 83.1%,
  2022 81.1%, 2023 58.6%, 2024 65.3%, 2025 70.6% (recent cohorts contain many deleted spam repos). Among
  found repos: 4.2% forks, 23.5% organization owners, 88.8% with a primary language; API `created_at` is
  never later than a day after the first observed star (0 violations).
- **Actor age** (ADR-016): 3,000 sampled real actor ids, 2,832 ok (168 deleted accounts, 404), 2,832
  breakpoints, ids 17 .. 342,334,107, estimated dates 2008-01-13 .. 2026-10-14. Hold-out (10%: 283 ids, fit
  on 2,549): **median absolute error 1.88 days, p90 4.40 days** (phase threshold 60). Median error by id decile
  (days): 3.9, 1.8, 1.6, 1.4, 1.4, 1.6, 1.6, 1.9, 2.2, 4.2 (oldest and newest deciles are the worst). The
  monthly top-up is scheduled in Phase 9.
- **Trending** (ADR-018): 1,522,558 rows after dedupe (hf_top_projects 108,120; antonkomarev 879,143; larsbijl
  535,283; github_trending 12), 4,360 distinct days 2013-08-21 .. 2026-10-16, 98.5% of rows resolved to a
  repo_id (1,500,208). Days with >= 1 entry per month (any source, any language list):

| year | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2013 | - | - | - | - | - | - | - | 2 | - | 2 | 1 | 1 |
| 2014 | - | 1 | - | 1 | 1 | 1 | - | 19 | 30 | 31 | 30 | 25 |
| 2015 | 31 | 28 | 31 | 30 | 30 | 29 | 30 | 29 | 30 | 29 | 29 | 17 |
| 2016 | 30 | 28 | 31 | 30 | 31 | 26 | 28 | 31 | 30 | 28 | 27 | 22 |
| 2017 | 30 | 27 | 30 | 29 | 30 | 27 | 31 | 26 | 28 | 29 | 28 | 31 |
| 2018 | 31 | 27 | 28 | 30 | 26 | 26 | 31 | 31 | 30 | 29 | 30 | 31 |
| 2019 | 30 | 28 | 31 | 30 | 31 | 29 | 31 | 31 | 30 | 31 | 29 | 22 |
| 2020 | 31 | 29 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2021 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2022 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2023 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2024 | 31 | 29 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2025 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2026 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 16 | - | - |

  Days with an **all-languages** list (`language_filter IS NULL`; the series the lead-time metric should
  use):

| year | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2013 | - | - | - | - | - | - | - | 2 | - | 2 | 1 | 1 |
| 2014 | - | 1 | - | 1 | 1 | 1 | - | 1 | 0 | 0 | 0 | 0 |
| 2015 | 1 | 4 | 2 | 1 | 0 | 1 | 1 | 2 | 0 | 0 | 0 | 0 |
| 2016 | 4 | 2 | 11 | 2 | 2 | 0 | 2 | 3 | 7 | 3 | 1 | 4 |
| 2017 | 5 | 3 | 4 | 2 | 8 | 3 | 5 | 2 | 3 | 7 | 3 | 5 |
| 2018 | 2 | 2 | 1 | 5 | 10 | 3 | 11 | 12 | 10 | 4 | 13 | 26 |
| 2019 | 28 | 27 | 29 | 29 | 31 | 11 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2020 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2021 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2022 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2023 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2024 | 31 | 29 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2025 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 31 | 30 | 31 |
| 2026 | 31 | 28 | 31 | 30 | 31 | 30 | 31 | 31 | 30 | 16 | - | - |

  Complete from 2020-01; 2019-07..2019-12 and most of 2014-2018 have only per-language lists (larsbijl).
- **HN** (ADR-019): 196,217 stories linking to github.com, 2015-01-01 .. 2026-10-16, 622 windows; 189,159
  (96.4%) parse to a repo URL and 161,087 (82.1% of stories) resolve to a repo_id. By year (stories /
  resolved): 2015 11,934 / 10,265; 2016 14,830 / 12,996; 2017 14,894 / 13,107; 2018 13,332 / 11,725; 2019
  13,367 / 12,056; 2020 15,761 / 14,071; 2021 12,316 / 10,973; 2022 13,141 / 11,785; 2023 15,915 / 14,444;
  2024 16,869 / 15,382; 2025 21,368 / 17,856; 2026 32,490 / 16,427. The 2025-2026 resolve rate drops because
  the WatchEvent name history is sparse after the 2025-05-24 capture collapse (ADR-009).
- **Upload:** all seven tables are in the derived repo under `enrich/` (~1.48 GB; commits of 1.38 GB and
  0.11 GB, within the caps).
- Deviations: repos fetched by node id instead of name + REST fallback (ADR-017); name history from
  WatchEvent only (ADR-016). Nothing outward beyond the approved pulls, uploads and API runs.

## Handoff to Phase 4 (state at 2026-10-16, commit 9440924; consumed by Phase 4)

Start a fresh session with: CLAUDE.md, this file, DECISIONS.md (ADR-009..015), ARCHITECTURE.md and
`docs/phases/PHASE_04_*.md`; then write the checklist plan and wait for the human's OK.

**Prerequisites: all met.** Phases 0-3 done. `GH_ENRICH_TOKEN` (classic, no scopes, 5,000 req/h) is in
`.env` and the Actions secrets; `HF_TOKEN`/`HF_USER` in `.env`, Actions secret `HF_TOKEN`, Actions variable
`HF_USER=Yasshh814`. The human pre-approved HF writes and Actions runs in the Phase 3 session; ask again
before creating anything new on the Hub or starting long Actions runs in a new phase.

**Where the data is**
- Hub (public): `Yasshh814/gh-breakout-events` (1,523 files, 114.91 GB, 5.59 G rows, 2015-01..2026-10-14,
  `catalog.parquet` at the root, README card), `-derived`, `-snapshots`, `-models` (cards only so far).
- Local: `data/` -> Lexar SSD. `data/lake` holds only the `bq` history (2015-01..2023-05, 60 GB) and the
  20 Phase 1 test-day files; the hourly era (2023-06..) is **on the Hub only**. Fetch what a phase needs with
  `uv run breakout lake pull --types WatchEvent,... --since YYYY-MM-DD [--until ...] [--push-daily]
  [--to DIR] [--manifests]` (it downloads exactly the files covering the range, into `data/lake` by default).
- `HF_HOME` is `data/hf_home` (SSD), scratch is `data/tmp`.

**Facts that matter for Phase 4+**
- Trusted era ends 2025-05-23 (`history.trusted_end`); later months are degraded (WatchEvents collapse,
  ADR-009). Stars after that date must come from API `stargazerCount` snapshots (stargazer listing is
  restricted, ADR-010). 2 hours are missing upstream (2025-06-12 17:00, 18:00).
- Tier B detail columns exist only from 2023-06-01 (`detail_level = 1`); earlier rows are spine-only.
- 2026-10 is published as `day-` files; the daily job (Phase 9) must append day files and compact the
  month with `lake compact --month` when complete (it also needs `lake pull --manifests` first).
- The repo is ~115 GB; HF free storage is best-effort (ADR-014 item 5). Do not add large tables to the
  events repo; derived tables go to `gh-breakout-derived`.
- Use `breakout.lake.hf` / `breakout.lake.sync` for any Hub access (retries, commit-size caps, catalog
  consistency, protected snapshots repo). Commits must stay <= 1.5 GB / 80 files or the client OOMs.
- No `LICENSE` file for the code yet (human: decide after Phase 10).

## Phase 3 status (2026-10-15)

- Done and verified: `lake/{hf,catalog,sync,compact,cards,backfill_month}.py`, extended `lake verify`, CLI
  `lake init|push|pull|compact|verify|catalog|backfill-month|backfill-gap-days`, workflow
  `.github/workflows/hourly-backfill.yml`, runbook lake section, ADR-015, tests in `tests/lake/`.
- Hub: 4 public repos under `Yasshh814/` (`gh-breakout-events|derived|snapshots|models`), cards served
  (license MIT per ADR-013, size category 1B<n<10B, 10 configs). `catalog.parquet` present.
- Bootstrap upload: 943 files, 60.68 GB, 3,260,735,374 rows (events 2,427,271,574 in 842 files / 45.9 GB;
  push_daily 833,463,800 in 101 files / 14.8 GB), 44 commits, 2015-01-01 .. 2023-05-31.
- Pull test: `lake pull --types WatchEvent --since 2023-03-01 --until 2023-05-31` fetched exactly 3 files
  (0.51 GB); the phase DuckDB query gives identical results on the pulled files and on `hf://`.
- Actions variable `HF_USER=Yasshh814` set. Hourly-era backfill **done** (run 38680271855, 41/41 jobs,
  ~22 h): events repo now 1,523 files, 114.91 GB, 5,592,548,999 rows (events 3,969,741,484 / 80.5 GB;
  push_daily 1,622,807,515 / 34.4 GB), 2015-01..2026-10-14; 2026-10 as day files; 42 manifest fragments
  (29,662 ok hours, 2 missing: 2025-06-12 17:00, 18:00). Smoke test (2023-06): 1 job, 65 min.
- `lake verify --remote`: 963 local files OK, 0 opendigger files, 0 remote problems.
- Open: HF free storage is best-effort and the repo is now ~115 GB; watch for throttling (ADR-014 item 5).
- Still pending: `LICENSE` file for the code (deferred by the human until after Phase 10).

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
- (Phase 2 ops) BigQuery backfill wall clock ~18 h on one worker under a 4 GB cap; merge peak RSS 1.0-1.9 GB; 4 failed attempts fixed by per-day finalization (ADR-012)
- (Phase 3) Lake size on HF (GB), file count: 114.91 GB, 1,523 data files (+ catalog, README, 42 manifest fragments); 5,592,548,999 rows. Bootstrap (bq) part: 60.68 GB / 943 files; hourly era +54.2 GB / 580 files
- (Phase 6, superseded by the ADR-024 correction, see "Phase 6 status") Candidates per snapshot (median), positive rate: median 4,990.5 candidates per snapshot (486 matured snapshots, 2016-01-04 .. 2025-04-21); positive rate 0.510% pooled, 0.505-0.518% per year (`breakout_rel`); 7,759 distinct positive repos. Baseline B1 (7-day velocity) pooled over 29 test folds (2018-02..2025-05): PR-AUC 0.0520 [0.0491, 0.0551], ROC-AUC 0.821, P@10 0.145, P@25 0.120 [0.113, 0.127], P@50 0.095; B2 PR-AUC 0.0405 / P@25 0.109; B3 PR-AUC 0.0447 / P@25 0.116. P@25 by year (B1): 2018 .092, 2019 .110, 2020 .120, 2021 .115, 2022 .124, 2023 .137, 2024 .133, 2025 (to Apr) .147. Lead time vs Trending (B1, top-25): 2,836 trending repos, 75.2% never flagged, 11.7% flagged before Trending, 4.6% at least 7 days before, median lead 0 d (IQR 0..2).
- (Phase 7) Feature build: see "Phase 7 status". Training rows 3,098,574; 71 features; tastemaker base hit rate 4.85%.
- (Phase 8) Baseline vs model PR-AUC / precision@25 (pooled and per year): see "Phase 8 status" (B1 0.0286 / 0.109, model 0.108 / 0.241).
- (Phase 9) Daily job runtime (median):

## Open issues / TODO for the human

- **Review ADR-024** (Phase 6 correction): candidates now include repos with unknown metadata; the Phase 6 headline numbers changed (B1 PR-AUC 0.0520 -> 0.0286). The corrected labels are on the Hub.
- ~~ADR-011 hourly backfill~~ done 2026-10-16 (Actions matrix, 41 jobs). Nothing heavy runs locally. `data/staging` (5.4 GB) is safe to delete (ask the human first).

- ~~Approve the BigQuery spine extraction~~ done 2026-10-13.
- ~~Lake size over 60 GB~~ accepted (ADR-013). ~~HF_TOKEN Actions secret~~ set 2026-10-13. ~~Dataset license~~ MIT (ADR-013). `HF_USER` Actions variable set (2026-10-15). Still open: `LICENSE` file for the code (human deferred it until after Phase 10).
- Review the source-test result (NO-GO for OpenDigger) and tell me how to proceed with the live-source gate (ADR-010, item 5). I have not started item 5.
- The stargazers listing is no longer available to us (ADR-010); the capture check and the daily
  cross-check must use `stargazerCount` deltas instead.
- OpenDigger data license: none found; its rows stay out of the public dataset.
- Post-2025-10-07 PullRequest/Review events have no PR author, creation time or merged flag (ADR-007).
