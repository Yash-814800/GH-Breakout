# CLAUDE.md — Project rules for gh-breakout

This file is read automatically at the start of every Claude Code session. It is the
contract for how work happens in this repository. **Read it fully before doing anything.**

## 1. What this project is

**gh-breakout** predicts which young GitHub repositories are about to "break out"
(gain an unusual number of stars in the next 30 days) using the public GH Archive event
stream, and publishes a daily, free, public leaderboard website with an honest public
track record.

It is also a portfolio project. Code quality, data-quality tests, honest evaluation and
clear docs matter as much as the model itself.

## 2. Hard constraints (never violate)

1. **Everything runs for $0 with no credit card anywhere.** Allowed services:
   - GitHub (public repo, GitHub Actions standard runners, GitHub Pages, GitHub Releases)
   - Hugging Face Hub free account (public dataset + model repos)
   - Google BigQuery **sandbox** (no billing account) — used only locally, only for the
     one-time historical backfill
   - Public HTTP sources: data.gharchive.org, GitHub REST/GraphQL API with a free token,
     Hacker News Algolia API, Bluesky (optional)
   - Do **not** introduce Cloudflare R2, AWS, Vercel Pro, MotherDuck paid tiers, or any
     service that asks for a card. If you think you need one, STOP and ask the human.
2. **The repository is public.** Never commit secrets, tokens, `.env` files, service
   account keys, or BigQuery credentials. Secrets live in GitHub Actions secrets and in a
   local, git-ignored `.env`.
3. **Never commit data files to git** except the tiny allow-listed ones in section 7.
   Data lives in `data/` locally (git-ignored) and on Hugging Face.
4. **Never join or key on repository name.** Repos get renamed and transferred. Always
   use `repo_id` (and `actor_id` for users). Names are display-only.
5. **No future data in features (point-in-time correctness).** See section 5.
6. **No random train/test splits.** Only time-based (rolling-origin) splits with an
   embargo. See section 6.
7. **BigQuery: never `SELECT *`, always dry-run first, always set
   `maximum_bytes_billed`.** The `payload` column dominates cost; scan it at most once per
   month table. See `docs/bigquery_cost_plan.md`.
8. **Never fabricate API fields or schema.** If you are unsure whether a field exists in
   GH Archive for a given era, check `docs/schema_audit.md` (produced in Phase 1) or
   inspect a real sample. GitHub removed many payload fields on 2025-10-07.

## 3. Tech stack (fixed unless a phase says otherwise)

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Package/env manager | `uv` (always run things as `uv run ...`) |
| CLI | Typer, entry point `breakout` (package `src/breakout/`) |
| Query engine | DuckDB (Python API + CLI) |
| Transformations | dbt-core + dbt-duckdb, project in `dbt/` |
| Storage format | Parquet, ZSTD compression, hive-style partitions |
| Data lake host | Hugging Face dataset repos (public) |
| ML | LightGBM, scikit-learn (calibration, metrics), SHAP |
| Config | `config/project.yaml` (single source of truth) loaded via `breakout.config` |
| Lint/format | ruff (lint + format), mypy on `src/` (non-strict is fine) |
| Tests | pytest (+ dbt tests) |
| Orchestration | GitHub Actions (cron, UTC) |
| Website | Astro (static output) + Observable Plot + DuckDB-WASM, deployed to GitHub Pages |

Pin versions in `pyproject.toml` / `uv.lock` and `site/package-lock.json`. Use the latest
stable versions available at install time; do not guess version numbers from memory.

## 4. Repository layout (target — create pieces as phases require them)

```
.
├── CLAUDE.md                     # this file
├── README.md                     # public-facing project README
├── pyproject.toml / uv.lock
├── Makefile                      # thin wrappers around `uv run breakout ...`
├── .env.example                  # names of env vars, no values
├── config/
│   ├── project.yaml              # all tunable parameters
│   └── feature_dictionary.yaml   # feature names, descriptions, SHAP sentence templates
├── src/breakout/
│   ├── cli.py  config.py  logging.py  paths.py
│   ├── schema.py                 # slim event schema — single source of truth
│   ├── ingest/                   # gharchive hourly download+parse, manifests, BigQuery backfill
│   ├── lake/                     # Hugging Face upload/download, layout, compaction
│   ├── enrich/                   # GitHub GraphQL metadata, actor-id age map, trending, HN
│   ├── ml/                       # datasets, baseline, train, evaluate, calibrate, explain, registry
│   ├── detect/                   # fake-star / suspicious growth
│   ├── publish/                  # site data export, ledger, RSS, badges, bluesky
│   └── ops/                      # health checks, drift, status page data
├── dbt/                          # dbt project (staging / intermediate / marts)
├── site/                         # Astro website
├── tests/                        # pytest; fixtures in tests/fixtures/
├── docs/
│   ├── phases/                   # PHASE_XX_*.md build prompts: local only, git-ignored, not in the public repo
│   ├── ARCHITECTURE.md  DECISIONS.md  PROGRESS.md  HUMAN_SETUP.md
│   ├── schema_audit.md           # produced in Phase 1
│   ├── bigquery_cost_plan.md     # produced in Phase 2
│   ├── data_dictionary.md  model_card.md  runbook.md
├── ledger/predictions.csv        # tamper-evident daily prediction ledger (tiny, committed)
├── status/heartbeat.json         # tiny, committed daily (keeps scheduled workflows alive)
└── .github/workflows/
```

## 5. Time semantics (read twice)

- **All timestamps are UTC.** Store as `TIMESTAMP` (naive, documented as UTC) or
  `TIMESTAMPTZ` consistently — choose once in Phase 1 and record it in `docs/DECISIONS.md`.
- **Snapshot date `D`** means "the world as known at `D 00:00:00 UTC`". Features for `D`
  may use only events with `created_at < D`. Never `<=`.
- **Labels for `D`** use events in `[D, D + horizon_days)` (default 30 days).
- A label for `D` is **matured** only when `D + horizon_days <= latest fully ingested day + 1`.
  Never train on or evaluate against unmatured labels.
- Any feature that itself depends on outcomes (e.g. tastemaker score, owner's prior
  breakouts) may only use labels that **matured before `D`**.
- The daily live run scores snapshot `D = today (UTC)` using data through the end of
  yesterday.

## 6. Modeling rules

- The candidate universe is defined in `config/project.yaml` (`candidates:`) and must be
  computed by **the same SQL** for training and for daily scoring.
- Evaluation is rolling-origin with an embargo of `labels.horizon_days` between the last
  training snapshot and the first test snapshot.
- Every model is compared against the baseline (7-day star velocity rank). A model that
  does not beat the baseline on PR-AUC and precision@k is not promoted.
- Calibration is fit on data that the model did not train on.
- Report metrics per year, not just pooled.
- Never use as a feature anything fetched "as of now" from the GitHub API that changes
  over time (current star count, current description, current topics). Only facts fixed
  at creation (`createdAt`, `isFork`) and slowly-varying, documented exceptions
  (`primaryLanguage`, owner type) are allowed, and each exception is recorded in
  `docs/DECISIONS.md`.

## 7. Files allowed in git that contain data

Only: `ledger/predictions.csv`, `status/heartbeat.json`, `dbt/seeds/*.csv` (small,
hand-maintained lists such as known bots), `tests/fixtures/*` (each fixture < 2 MB),
`config/*.yaml`, `reports/` (Markdown, small JSON metrics, PNG/JPEG figures < 500 KB each), `site/test-data/**`
(fixtures for the site build and tests) and `site/tests/**/__screenshots__/*.png` (Playwright snapshots, each < 300 KB).
Everything else data-like goes to Hugging Face or `data/`.

`.gitignore` must include at least: `data/` and `/data` (on the dev machine `data` is a symlink to the
external SSD and `data/` only matches directories), `.env`, `*.duckdb`, `*.duckdb.wal`,
`dbt/target/`, `dbt/logs/`, `site/node_modules/`, `site/dist/`, `site/public/data/`,
`__pycache__/`, `.venv/`, `*.parquet` (with explicit `!tests/fixtures/**` exceptions).

## 8. How to work in this repo (process rules for every session)

1. At session start: read `CLAUDE.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, and the
   phase file you were asked to implement. Do not start a phase whose prerequisites in
   `docs/PROGRESS.md` are not marked done — tell the human instead.
2. Make a short plan (bullets) before coding. Implement in small, testable steps.
3. Prefer DuckDB SQL over pandas for anything touching more than ~1M rows. Never load an
   entire event table into pandas.
4. Every new module gets unit tests. Every new dbt model gets at least `not_null` /
   `unique` tests on its grain.
5. Run before declaring a step done: `uv run ruff check . && uv run ruff format --check .
   && uv run pytest -q` (and `uv run dbt build` inside `dbt/` once dbt exists).
6. Log, don't print. Use the project logger (`breakout.logging.get_logger`).
7. All CLI commands must be **idempotent**: running twice produces the same result and
   no duplicates.
8. When a phase is complete, update `docs/PROGRESS.md` (checklist + notes + any numbers
   measured) and append any decisions to `docs/DECISIONS.md` (ADR style: context,
   decision, consequences). Then commit with a conventional commit message
   (`feat(ingest): ...`).
9. If something in a phase file is wrong or impossible (an API changed, a limit changed),
   do not silently work around it. Record it in `docs/DECISIONS.md`, choose the most
   conservative fix, and tell the human in your final message.
10. **STOP and ask the human** when: a step needs a credential or account action; any
    cost could become non-zero; data volume exceeds the limits stated in a phase; a
    destructive operation on Hugging Face (delete, squash) is needed; or a design decision
    is marked "HUMAN DECISION" in a phase file.

## 9. Glossary

- **Spine columns**: `event_id, event_type, created_at, repo_id, repo_name, actor_id,
  actor_login, org_id`. Cheap to extract from BigQuery, available for all eras.
- **Detail columns**: fields parsed from the JSON `payload` (action, issue/PR number,
  merged flag, ref_type, ...). Expensive in BigQuery; era-dependent.
- **detail_level**: 0 = spine only, 1 = payload parsed.
- **Candidate**: a repo eligible to be scored on snapshot `D` (young, small, starting to move).
- **Breakout**: the positive label (see `labels:` in config).
- **Matured label**: a label whose horizon has fully elapsed and been ingested.
- **Tier A / B / C features**: A = spine-only (all history), B = needs detail columns,
  C = external enrichment (GitHub API metadata, HN).

## 10. Machine, storage and security rules (added 2026-10-13, ADR-011/012/013; updated 2026-10-16, ADR-015)

The developer machine has 15 GB RAM and a previous heavy ingest crashed Claude Code. Treat
local resources as scarce.

1. **Heavy jobs run under a hard cap**, e.g. `systemd-run --user --scope -p MemoryMax=4G
   -p MemorySwapMax=0 -p CPUQuota=100% uv run breakout ...`, with one worker. Never run the
   hourly backfill (~2 TB download) on the laptop: it ran as a GitHub Actions matrix (`hourly-backfill`,
   done 2026-10-16, ADR-011); re-running it is safe and skips finished months. Do not start long jobs in the foreground; run them in the background and
   report progress.
2. **DuckDB statements over lake data** use a fresh connection per statement with
   `SET memory_limit='1500MB'`, `SET threads=1` and `SET temp_directory=<data/staging/...>`.
   Never `DISTINCT ON (...) *` plus a second global `ORDER BY` over a month of wide rows (it OOMs);
   dedupe per day, then a sort-only pass (see `ingest/bq/run.py`, ADR-012). Measure peak RSS on
   real data before launching long runs.
3. **`data/` is a symlink to `/run/media/yash/Lexar SSD/gh-breakout/data`** (NTFS, same physical disk
   as `/home`, not a backup). If the SSD is not mounted, stop and tell the human. Do not delete
   anything under `data/` without asking; the SSD copy is the only local copy of the lake.
4. **Secrets**: tokens are in git-ignored `.env` and GitHub Actions secrets (`HF_TOKEN`,
   `GH_ENRICH_TOKEN` exist). Never print, log or commit a token; compare or validate them without
   echoing. If a user pastes one in chat, say it is exposed and suggest rotation.
5. **Account/outward actions need explicit approval each time**: creating or deleting Hugging
   Face repos, uploads, `gh secret set`, pushes. The human has approved the HF token as an Actions
   secret (done), MIT as the dataset-card license (ADR-013) and a lake larger than 60 GB.
6. **Long-running state is resumable.** Always read the manifest (`data/manifests/*.json`,
   `data/lake/manifests/hourly_manifest.parquet`) before launching, and say what remains.
7. **Hugging Face lake (Phase 3, ADR-015).** The events repo `Yasshh814/gh-breakout-events` holds the whole
   lake (hourly era only there; local `data/lake` has just the `bq` history). Move data with
   `breakout lake pull|push|compact|verify` and `breakout.lake.{hf,sync}` only: they cap commits at
   1.5 GB / 80 files (larger commits OOM the client), keep `catalog.parquet` consistent and never delete
   in the snapshots repo. Run uploads detached under a cap (`setsid nohup systemd-run --user --scope -p
   MemoryMax=3G -p MemorySwapMax=0 ...`) and check liveness with `systemctl --user is-active <scope>`,
   not `pgrep -f`. `HF_HOME` is `data/hf_home` and scratch is `data/tmp`, both on the SSD. Do not pull
   the whole lake; pull only the types and dates a step needs.
8. **Repo and Actions actions** (create/delete HF repos, uploads, `gh workflow run`, pushes) need explicit
   approval in each new session; the human's Phase 3 approvals do not carry over.
9. **Long dbt jobs run from a frozen copy of `dbt/`** (Phase 7, ADR-023): `cp -r dbt ~/.cache/ghb-dbt-snapshot` and set
   `GHB_DBT_DIR`, `DBT_TARGET_PATH`, `DBT_LOG_PATH` to it. Every bucket is a separate `dbt` call that compiles the whole project, so
   an edit of any model while the job runs aborts it. The warehouse build copy lives in `~/.cache/ghb-warehouse/` (local disk), the
   finished file is copied to `data/warehouse.duckdb`.
