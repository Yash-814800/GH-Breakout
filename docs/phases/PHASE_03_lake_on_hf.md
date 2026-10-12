# Phase 03 — The lake on Hugging Face (layout, upload, sync, compaction, catalog)

## Goal
Publish the local Parquet lake to free, public Hugging Face dataset repos, and build the tools
every later phase uses to move data between the laptop / GitHub Actions and Hugging Face:
upload (batched, atomic commits), selective pull, monthly compaction, and a catalog of files.

## Prerequisites
- Phase 02 has finalized at least some months locally (Priority 1 or the `--since` slice).
- `HF_TOKEN` and `HF_USER` set locally.

## Background you must know
- Free accounts get best-effort free **public** storage; HF asks that large public datasets be useful
  to others and have a dataset card. Keep the total lake well under ~60 GB.
- Repo guidance: < 100k files per repo, < 10k entries per folder, ~50–100 files per commit, avoid
  thousands of tiny commits. Commits via `HfApi.create_commit` with `CommitOperationAdd` /
  `CommitOperationDelete` are atomic — use them for compaction (add month file + delete day files in
  one commit).
- Browsers cannot reliably do cross-origin range requests against HF file URLs, so the website will
  NOT read from HF directly (see Phase 10). Python/DuckDB can read HF fine.

## Repos (create idempotently with `HfApi.create_repo(..., repo_type=..., exist_ok=True, private=False)`)
| Config key | Type | Contents |
|---|---|---|
| `huggingface.events_repo` | dataset | `events/...`, `push_daily/...`, `manifests/...`, `catalog.parquet`, `README.md` |
| `huggingface.derived_repo` | dataset | `enrich/...` (Phase 4), `features/...`, `labels/...`, `training/...` (Phases 6–8) |
| `huggingface.snapshots_repo` | dataset | `predictions/date=YYYY-MM-DD/predictions.parquet` (Phase 9). **Never squash, never rewrite.** |
| `huggingface.models_repo` | model | `models/<version>/...`, `registry.json`, model card |

## Deliverables
1. `src/breakout/lake/hf.py`:
   - `get_api()` (token from env), `ensure_repos()`.
   - `upload_files(repo_key, pairs: list[(local_path, path_in_repo)], message, deletes: list[str]=[])`:
     splits into commits of ≤ `huggingface.max_files_per_commit`, retries on HTTP 5xx / 429 with
     backoff (tenacity), skips files whose sha256 already matches the remote (use the catalog, see 3,
     not one API call per file). Returns commit ids.
   - `download_files(repo_key, paths_in_repo, local_root)` using `hf_hub_download` with
     `local_dir=` so the local layout mirrors the repo; parallel (thread pool, 8 workers); skip if the
     local file exists with matching size+sha from the catalog.
   - `remote_list(repo_key, prefix)` via `HfApi.list_repo_tree(recursive=True)` (paginated).
2. `src/breakout/lake/catalog.py`:
   - `build_catalog(local_root) -> table` with one row per Parquet file: `path, table (events|push_daily),
     event_type, year, month, kind (bq|day|month), day (nullable), rows, bytes, sha256, min_created_at,
     max_created_at, detail_level_min, detail_level_max, schema_version`. Use Parquet metadata for row
     counts (do not scan data).
   - Uploaded as `catalog.parquet` at the events repo root in the same commit as data changes.
   - `select_files(catalog, table, event_types, start_day, end_day)` → list of paths needed to cover
     a date range (month/bq files that overlap + day files in range).
3. CLI:
   - `breakout lake init` → `ensure_repos()` + writes/updates dataset cards (deliverable 6).
   - `breakout lake push [--table events|push_daily|all] [--since YYYY-MM]` → uploads local files that
     are new or changed, plus manifests and catalog.
   - `breakout lake pull --types WatchEvent,ForkEvent --since 2026-06-01 [--until ...] [--push-daily]`
     → downloads only files covering that range (uses remote catalog).
   - `breakout lake compact --month YYYY-MM` → for every event type (and push_daily): if the month is
     complete (all its days have day files and the hourly manifest shows no `pending` hours for that
     month), merge `day-*.parquet` into `month-YYYYMM.parquet` (DISTINCT ON event_id; sort by
     `repo_id, created_at`; target ~`lake.target_file_mb`; if a file would exceed 1 GB, split into
     `month-YYYYMM-part001.parquet`, …). Then one atomic HF commit: add month files, delete day files,
     update catalog. Locally delete day files after the commit succeeds.
   - `breakout lake verify` → compares local vs remote catalog and checks invariants (deliverable 5).
4. Bootstrap upload of the Phase 2 history: `breakout lake push --table all`. Upload in month order;
   print progress and total GB. If total exceeds 60 GB, STOP and ask.
5. Invariants checked by `lake verify` (also unit-tested on a synthetic lake):
   - No two files cover the same `(event_type, day)` (bq/month files cover whole months; day files
     must not exist for months that have a bq or month file).
   - Every file's `schema_version` equals `schema.SCHEMA_VERSION`; columns match `schema.events`
     exactly (names and types).
   - No duplicate `event_id` within a file (cheap check via DuckDB `COUNT(*) = COUNT(DISTINCT event_id)`
     — run only with `--deep`, it scans data).
   - Months before `history.cutover_date` come from `bq` (or `month` if hourly-detail was used);
     months from cutover onward come from `day`/`month` files.
6. Dataset cards (`README.md` in each dataset repo, generated from templates in `src/breakout/lake/cards/`):
   YAML front matter with `configs` so the HF dataset viewer can load `events` by event type,
   pretty name, tags (`github`, `gharchive`, `parquet`), size category. Body: what it is, provenance
   (GH Archive → GitHub Events API; link gharchive.org), schema table (generated from `schema.py`),
   coverage (generated from the catalog: date ranges, detail coverage), known caveats (payload trimming
   on 2025-10-07, unstars not recorded, bots included), update cadence, and how to query with DuckDB
   (`hf://datasets/<repo>/events/event_type=WatchEvent/**/*.parquet`). **License field: HUMAN DECISION** —
   leave a TODO and ask the human; do not assert a license on their behalf.
7. Tests with a temp directory and a fake `HfApi` (monkeypatch) for upload batching, skip-if-unchanged,
   compaction (day files → month file → deletes), and catalog selection logic.

## Rules / gotchas
- One commit per logical change; never one commit per file.
- Never delete or squash anything in `snapshots_repo`.
- Compaction must be idempotent: running it twice on a compacted month is a no-op.
- The events repo will accumulate commits from the daily job (~1–2/day). Document in
  `docs/runbook.md` that a yearly `super_squash_history` on the **events** repo (not snapshots) is
  allowed after HUMAN approval, and that the git ledger (Phase 9) keeps the audit trail.
- Hive partition values: `event_type=WatchEvent`, `year=2024`, `month=06`.

## Acceptance criteria
- [ ] Four HF repos exist and are public; dataset cards render (open the URLs and confirm).
- [ ] `breakout lake push` uploaded the history; `catalog.parquet` present; total size recorded in PROGRESS.
- [ ] From a clean temp dir: `breakout lake pull --types WatchEvent --since <3 months ago>` downloads only the
      needed files, and this DuckDB query works on the pulled files:
      `SELECT date_trunc('day', created_at) d, count(*) FROM read_parquet('data/lake/events/event_type=WatchEvent/**/*.parquet', hive_partitioning=true) GROUP BY 1 ORDER BY 1 DESC LIMIT 5`.
- [ ] Same query works directly against `hf://datasets/<events_repo>/events/event_type=WatchEvent/year=<Y>/month=<M>/*.parquet`.
- [ ] `breakout lake verify` passes; compaction test passes.
- [ ] `docs/runbook.md` created with lake operations (push, pull, compact, verify, squash policy).
