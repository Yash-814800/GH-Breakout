# Architecture

## One-paragraph summary

A one-time **historical backfill** pulls slim GH Archive events (2015-01 → 2023-05, spine columns
only) from the public BigQuery dataset using a free, card-less BigQuery sandbox, run from the
developer's laptop under a memory cap (done 2026-10-13, 57 GB). From the cutover date
(2023-06-01) onward, the history **and** the **daily GitHub Actions job** download GH Archive
hourly files directly (the ~2 TB hourly backfill itself runs as an Actions matrix, ADR-011), parses them into the same slim schema, appends them to a Parquet
lake hosted on **Hugging Face** (public dataset), rebuilds features for candidate repos
with **dbt + DuckDB**, scores them with a **LightGBM** model stored on Hugging Face,
freezes the day's predictions into an immutable snapshot + git ledger, and deploys a
static **Astro** site to **GitHub Pages**. A weekly workflow retrains and promotes a model
only if it beats the current champion and the baseline.

## Data flow

```
                      ONE-TIME (laptop)                                  DAILY (GitHub Actions, public repo)
 ┌──────────────────────────────┐                         ┌────────────────────────────────────────────┐
 │ BigQuery sandbox             │                         │ data.gharchive.org/YYYY-MM-DD-H.json.gz     │
 │ githubarchive.month.YYYYMM   │                         │ (H is NOT zero-padded: 0..23)               │
 └──────────────┬───────────────┘                         └───────────────────────┬────────────────────┘
                │ spine (+ detail when budget allows)                              │ download, parse (same parser)
                ▼ Storage Read API (free for query results)                        ▼
        ┌──────────────────────────────────────────────────────────────────────────────────┐
        │  Slim event lake (Parquet, ZSTD, hive partitions)   ── Hugging Face: gh-breakout-events │
        │  events/event_type=X/year=YYYY/month=MM/*.parquet ;  push_daily/year=/month=/          │
        └──────────────────────────────────────┬───────────────────────────────────────────┘
                                               │ dbt-duckdb (staging → intermediate → marts)
     enrichment (GitHub GraphQL repo metadata, actor-id→age map, trending history, HN) ──┤
                                               ▼
        ┌──────────────────────────────────────────────────────────────────────────────────┐
        │ mart_candidates · mart_repo_features (point-in-time) · mart_labels · mart_leaderboard │
        │                                   ── Hugging Face: gh-breakout-derived              │
        └──────────────────────────────────────┬───────────────────────────────────────────┘
                     weekly retrain ◄──────────┤──────────► daily score (champion model)
              (gh-breakout-models)             │                 │
                                               ▼                 ▼
                         frozen predictions (gh-breakout-snapshots) + ledger/predictions.csv (git)
                                               │
                                               ▼
                         Astro static site on GitHub Pages: leaderboard, repo pages, track record,
                         explorer (DuckDB-WASM over same-origin Parquet), methodology, status, RSS, badges
```

## Where data lives (as of 2026-10-13)

| Place | What | Notes |
|---|---|---|
| `data/` (symlink → Lexar SSD NTFS partition) | lake (`bq-*`, `day-*`), manifests, staging, parity, audit | not in git; not a backup; same physical disk as `/home` (ADR-012) |
| Hugging Face dataset/model repos | the published lake, derived tables, snapshots, models | second copy; created in Phase 3 |
| GitHub Actions | hourly backfill matrix, daily pipeline, weekly retrain | secrets `HF_TOKEN`, `GH_ENRICH_TOKEN` |
| Git | code, config, ledger, heartbeat, reports | tiny files only (CLAUDE.md §7) |

Coverage: 2015-01..2023-05 BigQuery spine (`detail_level` 0, `source='bq'`); 2023-06-01 onward hourly
parser (`detail_level` 1, `source='hourly'`); trusted data ends 2025-05-23, later days are degraded
(ADR-009/010). Local resource limits and the memory-bounded merge design are in CLAUDE.md §10 and ADR-012.

## Why these choices (free, no card)

| Need | Choice | Why not the alternative |
|---|---|---|
| Historical extraction | BigQuery sandbox (1 TB scanned/month, no card) + Storage Read API (reading query results is free) | Downloading ~10 years of hourly JSON is many TB of transfer |
| Ongoing ingestion | GH Archive hourly files in GitHub Actions | Public repos get free, unlimited standard-runner minutes (4 vCPU / 16 GB RAM / 14 GB SSD, 6 h job limit) |
| Lake storage | Hugging Face public datasets | Cloudflare R2 requires a card; HF public storage is free (best-effort, use responsibly, needs a dataset card) |
| Compute engine | DuckDB | No server; runs on laptop and in Actions |
| Site hosting | GitHub Pages | Same repo, no extra account/token; deploy from Actions artifact |
| Browser SQL | DuckDB-WASM over Parquet served **from the site itself** | Hugging Face's CDN does not reliably allow cross-origin range requests |
| Model registry | Hugging Face model repo (+ `registry.json`) | Card-free, versioned, has a model card |

## Data volume strategy

- PushEvent is ~half of all events: stored only as `push_daily` aggregates.
- Detail (payload) columns exist only from `history.detail_start_date` onward (budget-limited)
  and from the daily pipeline. Features are tiered (A spine-only, B detail, C enrichment) so
  the model degrades gracefully where detail is missing (LightGBM handles NaN natively).
- Historical feature building is **candidate-first**: compute daily star counts first, find
  `(repo_id, snapshot_date)` candidate pairs, and compute expensive features only for those repos.
- The daily job needs only the last `daily.recent_window_days` of data and streams partitions
  from Hugging Face, filtering to candidate repos and their stargazers.

## Key external facts (verified Oct 2026 — re-verify if something fails)

- GitHub trimmed Events API payloads on 2025-10-07: PushEvent commit lists/counts removed,
  pull-request payloads trimmed, `author_association` removed from PR/issue/comment/review events.
- BigQuery sandbox: 10 GB storage, 1 TB query processing per month, tables expire after 60 days,
  no DML/streaming. Queries simply fail when the quota is exhausted (no charges without billing).
- Scheduled workflows in public repos are disabled after 60 days without repository activity;
  scheduled runs can be delayed.
- GitHub Pages: ~1 GB published site limit, soft bandwidth limit ~100 GB/month.
- Hugging Face repos: keep < 100k files per repo, < 10k entries per folder, ~50–100 files per commit.
