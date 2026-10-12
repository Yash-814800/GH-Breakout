# Decision log (ADR-style)

Append new decisions at the bottom. Never rewrite old ones; supersede them with a new entry.
Format: `## ADR-NNN: Title (YYYY-MM-DD)` then **Context**, **Decision**, **Consequences**.

## ADR-001: Zero-cost, no-card infrastructure (2026-10-12)
**Context:** The project must run for $0 with no credit card on any service.
**Decision:** GitHub (public repo, Actions, Pages, Releases), Hugging Face public datasets/models,
BigQuery sandbox for the one-time backfill only (run from the laptop), DuckDB + dbt for compute.
**Consequences:** No Cloudflare R2/S3. Lake storage must stay modest (target < 60 GB total) and the
dataset must be documented as a reusable public dataset. HF browser CORS limits mean the site serves its
own Parquet for DuckDB-WASM.

## ADR-002: Hybrid backfill — BigQuery spine for all history, payload detail budget-limited (2026-10-12)
**Context:** BigQuery bills by bytes of the columns scanned. The JSON `payload` column is most of the
bytes; scanning it for 2015→2026 would take several months of the free 1 TB quota.
**Decision:** Extract spine columns for all months (cheap). Extract payload-derived detail columns
newest-first while the monthly budget allows, in the same query as the spine for that month so payload is
scanned once. Record coverage in a manifest; resume next month. Optionally fill older detail from hourly
files on the laptop.
**Consequences:** Features are tiered. `history.detail_start_date` marks where Tier B features begin.

## ADR-003: Events API payload trimming on 2025-10-07 (2026-10-12)
**Context:** GitHub removed push commit lists/counts, many pull-request fields, and `author_association`.
**Decision:** Phase 1 audits payload keys per era. Features never rely on `author_association`;
"maintainer"/"first-time contributor" are computed from our own history. PR merge features use whatever
the audit shows is still present, with explicit era flags.
**Consequences:** Some Tier B features change definition across the cutoff; models include an
`era_post_2025_10` indicator and the evaluation reports post-cutoff performance separately.

## ADR-004: GitHub Pages + Astro for the site (2026-10-12)
**Context:** Need a free static host; data refreshed daily.
**Decision:** Astro static build, deployed from the daily workflow with `actions/deploy-pages`.
Vercel Hobby / Cloudflare Pages documented as alternatives.
**Consequences:** Site must respect the GitHub Pages project base path (`/<repo>/`).

## ADR-005: Timestamps are naive UTC `TIMESTAMP` (2026-10-12)
**Context:** CLAUDE.md section 5 requires choosing once between `TIMESTAMP` and `TIMESTAMPTZ`.
**Decision:** Store all event and snapshot times as naive `TIMESTAMP` that is documented as UTC; dates as `DATE`.
`project.timezone` is `UTC` in config.
**Consequences:** No timezone conversion anywhere in SQL or Python. Any ingest code must convert
tz-aware inputs to UTC and drop the tzinfo before writing.

## ADR-006: Config loading rules (2026-10-12)
**Context:** Tests and tooling must run without secrets, and the real `.env` must not leak into tests.
**Decision:** `breakout.config` is the only reader of `project.yaml`; it validates with pydantic
(`extra="forbid"`, so typos fail loudly). A `${VAR}` string with any unset variable becomes `None`;
`require_*` accessors raise only on use. `.env` is loaded only when the default config path is used,
never when an explicit path or `--config` / `BREAKOUT_CONFIG` is given. `training.embargo_days >=
labels.horizon_days` is enforced at load time.
**Consequences:** New YAML keys require a matching model field in the same change.

## ADR-007: Slim schema and hourly parser details (2026-10-12)
**Context:** Phase 1 had to freeze the event schema and pick parsing rules; the audit
(`docs/schema_audit.md`) measured which payload paths exist per era.
**Decision:**
- Timestamps follow ADR-005: `created_at` and `target_created_at` are naive UTC `TIMESTAMP`
  (written as `timestamp[us]` in Parquet); the parser casts through `TIMESTAMPTZ ... AT TIME ZONE 'UTC'`
  with the DuckDB session `TimeZone` forced to UTC. `event_type` is both a column and a hive key; DuckDB
  reads such files with `hive_partitioning=true` without conflict (verified).
- No era-specific path fallbacks were needed. The only `COALESCE`s are PR/review `number`
  (`payload.pull_request.number`, then `payload.number`; review events have no `payload.number`).
- `action` is extracted only for Watch/Issues/IssueComment/PullRequest/PullRequestReview/Release as
  specified. `ForkEvent.payload.action` exists only post-trim and is deliberately not extracted.
- `is_pull_request` is FALSE for IssuesEvent (GitHub never emits IssuesEvent for PRs; audited 0%).
- `pr_merged` is set only for PullRequestEvent with `action = 'closed'`.
- Rows missing `id`, `actor.id`, `repo.id` or `created_at` are dropped and counted as `bad_ids`
  (e.g. a ForkEvent with `repo: {}` on 2026-10-10). Malformed JSON lines are counted as `bad_json_lines`.
- Events outside the file's hour +-1h are kept (routed to their own day via spill files) and counted.
- The staged per-hour push rows carry `event_id` (not in the phase's column list) so boundary
  duplicates can be removed before daily aggregation; `push_daily.repo_name` is the name on the
  highest `event_id` of the group.
- Day files are a pure function of staged hours plus spill files; staging is kept after a build.
  An `ok` hour whose staged file is missing is re-ingested rather than building a partial day.
**Consequences:** `PARSER_VERSION = 1`; bumping it makes the manifest re-ingest hours. Staging
(~24 MB for a 2026 day) must be cleaned by the daily pipeline in Phase 9. Post-2025-10-07 PR
author, PR creation time and merged flag are NULL by construction (features must handle NaN).

## ADR-008: Star-event volume collapse in GH Archive since ~2026-03 (2026-10-12)
**Context:** Acceptance checks showed WatchEvent below IssuesEvent for whole days in 2026. Probing
hourly files directly (not through the parser) showed WatchEvent per 12:00 UTC hour: ~4,500
(2025-09/10), 3,264 (2026-02-15), 872 (2026-04-15), 119 (2026-06-15), 24 (2026-08-15, flat at
17-42 in every hour), 1,158 (2026-09-15), 346 (2026-10-10). Other event types are roughly normal.
**Decision:** Not worked around in Phase 1 (the parser is correct; this is the source data). Recorded
here and in PROGRESS "Open issues" for a human decision before Phase 2 sets `cutover_date` and
before any labels are built on post-2026-03 data.
**Consequences:** Labels based on star gains in the 2026 stream are not comparable with earlier
years; the daily pipeline's candidates/labels would be starved. Options for the human: accept
(model on <= 2026-02 data, treat live scoring as degraded), switch the star source for recent
data (GitHub API stargazers with timestamps for candidate repos), or investigate with GH Archive.
