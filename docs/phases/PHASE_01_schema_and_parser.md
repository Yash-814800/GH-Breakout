# Phase 01 — Payload audit across eras, slim schema, hourly parser

## Goal
1. Find out, from real data, which fields exist in each event type's payload in each era
   (2015 → today), especially before/after GitHub's 2025-10-07 payload trimming.
2. Freeze a **slim event schema** (the single source of truth for both BigQuery backfill and
   the daily pipeline).
3. Build a robust, idempotent **hourly-file ingester** that downloads one GH Archive hour,
   parses it into the slim schema, and writes Parquet into the local lake layout.

## Prerequisites
Phase 00 done.

## Background you must know
- Hourly files: `https://data.gharchive.org/YYYY-MM-DD-H.json.gz`. **H is not zero-padded**
  (`2024-06-01-0.json.gz` … `2024-06-01-23.json.gz`). Each line is one JSON event.
- Top-level fields: `id` (string of digits), `type`, `actor{id,login,...}`, `repo{id,name,url}`,
  `payload{...}` (varies by type and era), `public`, `created_at` (ISO-8601 UTC, `Z` suffix),
  optional `org{id,login,...}`.
- `WatchEvent` means "starred". Its payload is only `{"action":"started"}`. Unstars are not events.
- On 2025-10-07 GitHub trimmed payloads (push commits/size/distinct_size, many pull_request
  fields, `author_association`). **Do not assume any payload field exists — measure it.**
- A file occasionally 404s (GH Archive has a few genuine gaps) or appears late.

## Deliverables
1. `src/breakout/ingest/gharchive.py`
   - `hour_url(ts: datetime) -> str` (unpadded hour; assert ts is whole-hour UTC).
   - `download_hour(ts, dest_dir) -> DownloadResult` using `httpx` streaming with `tenacity`
     retries (exponential backoff, 5 attempts, retry on 5xx/timeouts, NOT on 404).
     404 → return status `missing`. Compute sha256 and byte size. Verify the gzip stream
     decompresses fully (read through it once); a truncated file → status `error`, delete it.
2. `scripts/audit_payloads.py` (or `breakout ingest audit` CLI) that:
   - Downloads these sample hours (12:00 UTC each): `2015-03-02`, `2016-06-01`, `2018-06-01`,
     `2020-06-01`, `2022-06-01`, `2024-06-03`, `2025-09-01`, `2025-11-03`, and **the most recent
     complete day available** (probe backward from now − 3h until a file exists).
   - For each hour and each event type in `events.raw_types + aggregated_types` from config:
     row count; and for every JSON path in `payload` up to depth 3 (e.g. `payload.issue.user.id`),
     the **presence rate** (share of events where the path exists and is not null).
     Use DuckDB `read_ndjson_objects(..., compression='gzip')` + `json_keys` / `json_structure`
     or a Python streaming pass — whichever is simpler; this is a small sample.
   - Writes `docs/schema_audit.md`: one section per event type, a table of paths × eras with
     presence %, and a "Parser decisions" subsection (see deliverable 4). Highlight every field
     whose presence drops below 50% after 2025-10-07.
   - Saves small **fixtures**: for each sampled era, up to 150 events per event type into
     `tests/fixtures/gharchive_<YYYY-MM-DD>-12.sample.json.gz` (keep each file < 2 MB; reduce
     the per-type cap if needed). These power the parser tests.
3. `src/breakout/schema.py` — the slim schema, as both a pyarrow schema and DuckDB DDL string,
   plus `SCHEMA_VERSION = 1` and `PARSER_VERSION = 1`:

   **Table `events` (one row per event, for `events.raw_types`)**

   | column | type | notes |
   |---|---|---|
   | event_id | BIGINT NOT NULL | `TRY_CAST(id AS BIGINT)`; drop rows where it fails, count them |
   | event_type | VARCHAR NOT NULL | also a hive partition key in files |
   | created_at | TIMESTAMP NOT NULL | UTC (decide naive-UTC vs TIMESTAMPTZ; record ADR) |
   | repo_id | BIGINT NOT NULL | |
   | repo_name | VARCHAR | display only |
   | actor_id | BIGINT NOT NULL | |
   | actor_login | VARCHAR | |
   | org_id | BIGINT | nullable |
   | detail_level | UTINYINT NOT NULL | 0 spine-only, 1 payload parsed |
   | action | VARCHAR | Issues/PR/Review/IssueComment/Release/Watch |
   | number | INTEGER | issue or PR number |
   | is_pull_request | BOOLEAN | IssueCommentEvent on a PR: `payload.issue.pull_request` present; PR/Review events: true |
   | target_user_id | BIGINT | issue author (`payload.issue.user.id`) or PR author (`payload.pull_request.user.id`) when present |
   | target_created_at | TIMESTAMP | issue/PR creation time when present |
   | pr_merged | BOOLEAN | PullRequestEvent closed: `payload.pull_request.merged` if present else NULL |
   | review_state | VARCHAR | PullRequestReviewEvent `payload.review.state` |
   | ref_type | VARCHAR | CreateEvent `payload.ref_type` (repository/branch/tag) |
   | forkee_repo_id | BIGINT | ForkEvent `payload.forkee.id` |
   | release_prerelease | BOOLEAN | ReleaseEvent `payload.release.prerelease` |
   | source | VARCHAR NOT NULL | `bq` or `hourly` |
   | ingested_at | TIMESTAMP NOT NULL | |

   **Table `push_daily` (PushEvent aggregated)**: `repo_id BIGINT, actor_id BIGINT, day DATE,
   n_pushes INTEGER, repo_name VARCHAR (last seen that day), source VARCHAR, ingested_at TIMESTAMP`.
   Grain: `(repo_id, actor_id, day)`.

   Adjust detail columns **only** if the audit proves a path is wrong (e.g. different key name in
   some era) — then implement era-specific fallbacks (`COALESCE(path_a, path_b)`) and document
   them. If the audit shows a field is absent in an era, it is simply NULL there; never impute.
4. "Parser decisions" in `docs/schema_audit.md`: for each detail column, the JSON path(s) used per
   era, presence after 2025-10-07, and which downstream features are affected.
5. `src/breakout/lake/layout.py` — paths for the local lake (mirrored 1:1 on Hugging Face later).
   Root = `cfg.lake.local_root`:
   - BigQuery history: `events/event_type={T}/year={YYYY}/month={MM}/bq-{YYYYMM}.parquet`
   - Daily (hourly-sourced) files: `events/event_type={T}/year={YYYY}/month={MM}/day-{YYYY-MM-DD}.parquet`
   - Compacted month (Phase 3): `events/event_type={T}/year={YYYY}/month={MM}/month-{YYYYMM}.parquet`
   - Push: same pattern under `push_daily/year={YYYY}/month={MM}/...`
   - Manifests: `manifests/hourly_manifest.parquet`, `manifests/bq_backfill.json`
   - Functions: `day_file(event_type, day)`, `bq_file(event_type, year, month)`,
     `glob_for(event_type, start=None, end=None)` returning a list of existing files or a glob string.
   - Month always two digits (`month=06`). Hive keys `event_type`, `year`, `month` only.
6. `src/breakout/ingest/parse.py`
   - `parse_hour_file(path, hour_ts) -> ParsedHour` returning two Arrow tables (`events`,
     `push_rows`) plus stats (lines read, rows kept per type, bad JSON lines, bad ids, duplicates).
   - Implementation: DuckDB `read_ndjson_objects(path, compression='gzip', ignore_errors=true)`
     → `json` column → `json_extract_string` / `json_extract` with explicit casts into the slim
     columns. One SQL statement per output table. Filter to configured types. Keep events whose
     `created_at` hour equals `hour_ts` **or** is within ±1 hour (GH Archive files can contain a
     few boundary events); do not drop them, but dedupe on `event_id`.
   - `detail_level = 1` for everything from hourly files.
   - PushEvent rows → `push_rows` (repo_id, actor_id, created_at, repo_name) — aggregated per day
     at write time (deliverable 7), not per hour.
7. `src/breakout/ingest/day.py` — `ingest_day(day, *, force=False)`:
   - For hours 0..23: skip hours already `ok` in the manifest with the current `PARSER_VERSION`
     (unless `force`); otherwise download → parse → stage per-hour Arrow results to
     `data/staging/{day}/hour={H}.parquet`.
   - After attempting all 24 hours, build the **day files** from all staged hours of that day:
     for each event type, `SELECT DISTINCT ON (event_id) ... ORDER BY event_id` and write
     `day-{YYYY-MM-DD}.parquet` (ZSTD, row groups ~128k rows, sorted by `repo_id, created_at`).
     Overwrite atomically: write to `*.tmp` then `os.replace`.
   - Push: aggregate staged push rows by `(repo_id, actor_id, CAST(created_at AS DATE))`.
   - Events whose `created_at` date ≠ `day` (boundary spillover) go to their own day's file on that
     day's next rebuild: write them into `data/staging/{their_day}/spill-from-{day}.parquet` and
     include spill files when building a day. Keep it simple but correct.
   - Update manifest rows for each hour: `hour_ts, status (ok|missing|pending|error), rows_kept,
     bytes, sha256, attempts, last_attempt_at, parser_version`. A 404 within
     `daily.late_hour_retry_days` of the hour → `pending`; older → `missing`.
   - Return a summary (counts per type, missing hours).
8. `src/breakout/ingest/manifest.py` — read/upsert the hourly manifest (Parquet via DuckDB), with
   `hours_needing_work(start, end, now)` implementing the pending/missing/retry rules.
9. CLI: `breakout ingest hour 2024-06-01T12`, `breakout ingest day 2024-06-01 [--force]`,
   `breakout ingest range 2024-06-01 2024-06-07 [--workers 2]`, `breakout ingest audit`.
10. Tests (`tests/ingest/`):
    - `hour_url` padding; timestamp validation.
    - Parser on every fixture: no exceptions; required columns non-null; `detail_level == 1`;
      dedupe works (duplicate a line in a temp fixture → one row out); WatchEvent `action='started'`;
      at least one IssueCommentEvent with `is_pull_request` true in eras where PR comments exist.
    - Post-2025-10-07 fixture: missing fields come out NULL, not errors.
    - `ingest_day` idempotency using a fake downloader that serves fixtures (monkeypatch):
      run twice → identical files (compare row counts + a checksum of sorted event_ids).
    - Manifest retry rules (pending → missing after N days) with a frozen clock.

## Rules / gotchas
- Never `json.loads` an entire hourly file into memory in Python. Use DuckDB or line streaming.
- Never key on repo_name. Never trust `public` (always true in archive).
- Bot filtering is NOT done here (staging layer, Phase 5). Ingest everything of the kept types.
- Delete raw downloads after successful parsing unless `--keep-raw` is passed.
- Keep `PARSER_VERSION` in sync: bump it whenever parsing logic changes; the manifest uses it to
  know what to re-ingest.

## Acceptance criteria
- [ ] `docs/schema_audit.md` exists with presence tables for all 9 sampled eras and parser decisions.
- [ ] `uv run breakout ingest day <a recent date>` completes, writes 9 event-type day files +
      push_daily file, manifest shows 24 `ok` hours (or explains missing ones).
- [ ] Running the same command again does no downloads and leaves files byte-identical (or
      identical by checksum of sorted content).
- [ ] Quick sanity query printed in your report: for that day, row counts per event type, and
      WatchEvent count vs `IssuesEvent` count look plausible (stars should be among the largest).
- [ ] All tests pass; fixtures each < 2 MB.
- [ ] ADR added for the timestamp type choice and any era-specific path fallbacks.
