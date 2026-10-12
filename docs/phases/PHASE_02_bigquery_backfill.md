# Phase 02 — BigQuery cost plan & historical backfill (2015 → cutover)

## Goal
Extract slim GH Archive history from the public BigQuery dataset into the local lake, using
only the free BigQuery sandbox (1 TB scanned per month, no billing account), with:
- a **measured cost plan** (dry runs are free),
- a **manifest** so the job resumes exactly where it stopped (including across calendar months
  when the quota runs out),
- spine columns for every month, detail columns newest-first while budget allows,
- an automated **parity check** proving BigQuery output equals the hourly parser's output.

This runs on the developer's laptop, never in GitHub Actions.

## Prerequisites
- Phase 01 done (`schema.py`, `layout.py`, parser, `docs/schema_audit.md`).
- `docs/HUMAN_SETUP.md` step 6 done: sandbox project exists, ADC login works, `GCP_PROJECT_ID` in `.env`.

## Background you must know
- Tables: `githubarchive.month.YYYYMM` and `githubarchive.day.YYYYMMDD` (also `githubarchive.year.YYYY`
  for early years). Schema: `type STRING, public BOOL, payload STRING (JSON), repo RECORD(id,name,url),
  actor RECORD(id,login,gravatar_id,avatar_url,url), org RECORD(...), created_at TIMESTAMP,
  id STRING, other STRING`.
- **Billing = bytes of the columns you reference, across all rows of the tables you touch.**
  `WHERE type = 'X'` does NOT reduce bytes. `LIMIT` does NOT reduce bytes. Referencing `payload`
  even once scans the whole payload column of that table. Therefore:
  - never `SELECT *`;
  - extract **all** needed detail fields for a table in **one** query (never one query per event
    type when payload is referenced);
  - always dry-run first and always set `maximum_bytes_billed`.
- Sandbox: queries fail with a quota error once 1 TB is used in the month — no charges can occur.
  Tables you create expire after 60 days and storage is capped at 10 GB, so **do not use
  destination tables**; read query results directly.
- Reading query results with the BigQuery Storage Read API is free (results live in temporary tables).
  Use `google-cloud-bigquery` with `google-cloud-bigquery-storage` and stream Arrow record batches.

## Deliverables
1. Add deps: `google-cloud-bigquery`, `google-cloud-bigquery-storage`, `db-dtypes` (if needed by
   the client for Arrow). Imports for these live only in `src/breakout/ingest/bq/` so the daily
   pipeline never needs them.
2. `src/breakout/ingest/bq/sql.py` — query builders (Jinja-free, plain f-strings with validated inputs):
   - `raw_events_sql(table_expr, mode)` where `mode ∈ {"spine","full"}`:
     ```sql
     SELECT
       SAFE_CAST(id AS INT64)            AS event_id,
       type                              AS event_type,
       created_at,
       repo.id AS repo_id, repo.name AS repo_name,
       actor.id AS actor_id, actor.login AS actor_login,
       org.id AS org_id
       -- full mode adds detail columns using JSON_VALUE / JSON_QUERY with the SAME paths and
       -- era fallbacks documented in docs/schema_audit.md, e.g.
       -- JSON_VALUE(payload, '$.action') AS action,
       -- SAFE_CAST(COALESCE(JSON_VALUE(payload,'$.issue.number'), JSON_VALUE(payload,'$.number'),
       --                    JSON_VALUE(payload,'$.pull_request.number')) AS INT64) AS number, ...
     FROM {table_expr}
     WHERE type IN UNNEST(@raw_types)
     ```
     In spine mode, detail columns are emitted as typed NULLs so the output schema always matches
     `schema.events`.
   - `push_daily_sql(table_expr)`:
     `SELECT repo.id, actor.id, DATE(created_at) AS day, COUNT(*) AS n_pushes, ANY_VALUE(repo.name)
      FROM {table_expr} WHERE type = 'PushEvent' GROUP BY 1,2,3`
   - `table_expr` for a chunk of days uses the day dataset with a wildcard:
     ``FROM `githubarchive.day.2024*` WHERE _TABLE_SUFFIX BETWEEN '20240601' AND '20240607'``
     (put the `_TABLE_SUFFIX` predicate in the WHERE clause together with the type filter).
   - Try a single combined script for raw + push and compare dry-run bytes against two separate
     queries; use whichever is cheaper and record the result in the cost plan.
3. `src/breakout/ingest/bq/survey.py` + CLI `breakout backfill survey`:
   - First verify table coverage: query `githubarchive.day.INFORMATION_SCHEMA.TABLES` (or list
     tables via the API) to confirm day tables exist for every day in range; report gaps. If day
     tables are missing for an era, fall back to month tables for that era.
   - For each month from `history.start_date` to the month before `cutover_date`, dry-run:
     (a) spine raw query, (b) full raw query, (c) push query. Record bytes.
   - Write `docs/bigquery_cost_plan.md`: a table per month (GB spine, GB full, GB push), yearly
     totals, grand totals, and the proposed **schedule** (deliverable 4). Also save machine-readable
     `data/manifests/bq_cost_survey.json`.
4. Planning policy (implement in `plan.py`, show in the cost plan, then **STOP for HUMAN DECISION**):
   - `cutover_date` default = the first day of the current UTC month (the daily pipeline will ingest
     from there with hourly files). Write it into `config/project.yaml` once approved.
   - Priority 1: **full** mode for the most recent 24 complete months.
   - Priority 2: **spine** mode for every remaining month back to 2015-01.
   - Priority 3 (future quota months): upgrade older months from spine → full, newest first.
   - Pack work into "quota months" of `bigquery.monthly_budget_bytes` each, in this priority order,
     newest first within each priority. Show which calendar month each unit of work lands in.
   - Report the resulting `detail_start_date` after quota month 1, and after all planned months.
   - Support `--since YYYY-MM` for the fast-start option (only plan months ≥ since).
5. `src/breakout/ingest/bq/run.py` + CLI `breakout backfill run [--since YYYY-MM] [--max-gb N] [--dry]`:
   - Work unit = (chunk of up to 7 days within one month, mode). Manifest
     `data/manifests/bq_backfill.json` records per unit: `month, chunk_start, chunk_end, mode,
     status (todo|running|done|failed), bytes_billed, rows_by_type, started_at, finished_at, job_id`.
   - Before each unit: dry-run; if `bytes + spent_this_calendar_month > monthly_budget_bytes`, stop
     cleanly and print "resume on <first day of next month>".
   - Run with `QueryJobConfig(maximum_bytes_billed=per_query_max_bytes_billed, use_query_cache=True,
     labels={"project":"gh-breakout"})`; record `job.total_bytes_billed`.
   - Stream results: `job.result().to_arrow_iterable(bqstorage_client=...)`; write record batches into
     `data/staging/bq/{YYYYMM}/{mode}/chunk-{start}-{end}/event_type={T}.parquet` (one ParquetWriter
     per event type, ZSTD). Add `detail_level` (0 spine / 1 full), `source='bq'`, `ingested_at`.
     Convert BigQuery TIMESTAMP to the timestamp type chosen in Phase 1.
   - When every chunk of a month (for the chosen mode) is done, **finalize the month**: for each event
     type, merge chunks with DuckDB (`DISTINCT ON (event_id)`, sort by `repo_id, created_at`) into
     `layout.bq_file(T, Y, M)` (atomic replace), merge push chunks into the push bq file (re-aggregate
     by grain in case a day spans chunks — it should not, but be safe), then delete the staging chunks.
   - If a month is upgraded spine → full, the full file replaces the spine file.
   - Quota error (`google.api_core.exceptions.Forbidden` / message containing "quota") → mark unit
     `todo`, stop cleanly. Any other error → retry once, then mark `failed` and continue with the next unit.
   - Ctrl-C safe: a unit is either `done` with files in place or not done.
   - Progress log: units done/remaining, GB spent this month, ETA.
6. Parity check — CLI `breakout backfill parity --day YYYY-MM-DD` (pick a day inside the most recent
   full-mode month):
   - Ingest that day via the Phase 1 hourly pipeline into a temp lake root, and extract the same day
     via BigQuery in full mode into another temp root (cost: one day ≈ small).
   - Compare per event type: row counts (must match within 0.1%), set difference of `event_id`s,
     and for 1,000 random shared event_ids every column must be equal (allow timestamp equality to the
     second). Write a report `docs/parity_report.md`. Any systematic mismatch is a bug — fix the SQL or
     the parser until parity holds. **This proves train/serve consistency.**
7. Optional (only if the human asks): `breakout backfill hourly-detail --start YYYY-MM --end YYYY-MM
   --workers 4` that runs the Phase 1 `ingest_day` for every day of those months on the laptop and then
   replaces the month's `bq-*.parquet` spine file with a full-detail month file (build it from the day
   files, then delete the day files). Throttle to ≤ 4 concurrent downloads. Mark the manifest
   `mode=full, source=hourly`.
8. Tests: SQL builders produce the expected column list in both modes (string tests), planner packing
   logic (pure function tests with fake survey numbers), manifest state machine, month finalization
   on small synthetic Arrow tables. No test may call BigQuery.

## Rules / gotchas
- Never run a non-dry query before the human approves the cost plan.
- Never reference `payload` in spine mode. Grep your SQL in a unit test to enforce this.
- Never use `SELECT *`, `ORDER BY` over full tables, or destination tables.
- Use `SAFE_CAST`, not `CAST`, for ids/numbers from JSON.
- BigQuery's `JSON_VALUE` returns NULL for non-scalars; use `JSON_QUERY(...) IS NOT NULL` to test
  presence of objects such as `$.issue.pull_request`.
- Keep the Storage Read API client creation inside a function; credentials come from ADC only.
- Expect total lake size of very roughly tens of GB. If the projected local size exceeds 80 GB, STOP
  and report sizes per type/year so the human can decide what to trim.

## Acceptance criteria
- [ ] `docs/bigquery_cost_plan.md` with measured per-month bytes, totals, and a schedule; human approved
      it; `cutover_date` written to config; ADR recorded.
- [ ] `docs/parity_report.md` shows parity between BigQuery and hourly parsing for one day.
- [ ] At least the Priority-1 months (or the `--since` slice) are finalized under `data/lake/events/...`.
- [ ] Re-running `breakout backfill run` with nothing left to do performs zero queries.
- [ ] `docs/PROGRESS.md` records GB spent, rows per type per year (a small table), lake size on disk,
      `detail_start_date`, and the date when remaining work resumes.
