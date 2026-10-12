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

## ADR-009: Trusted era, capture-quality findings, and source strategy after the 2025-26 star-capture collapse (2026-10-12)
**Context:** ADR-008 found WatchEvent volume collapsing in GH Archive. Measured from BigQuery
(`reports/capture_quality.md`, 1,015 days, 53.8 GB scanned, `type` column only): stars per day
versus the same weekday's 2024 median is 0.97-1.16 through 2025-05-23, drops abruptly to 0.71 on
**2025-05-24**, sits at 0.55-0.75 through 2025-09, ~0.44 in 2025-10..2026-01, 0.30-0.37 in 2026-02..04,
0.12 in 2026-05 and 0.01 in 2026-07/08. Other event types stay near baseline (all-events ratio
0.68-0.76), so this is star capture, not overall volume. In September 2026 stars partially recover for
short stretches (0.48-0.74 on 2026-09-04..06) and collapse again. Upstream issue
igrigorik/gharchive.org#320 independently reports ~90-100% capture before June 2025 falling below 20%
in 2026 against the stargazers API; #323 announces the OpenDigger mirror (hourly files since
2026-09-06).
**Decision (human, 2026-10-12):**
1. `history.trusted_end = 2025-05-31`; `history.degraded_end = 2026-09-05`. Training, rolling-origin CV
   and backtests use only snapshots D with `D <= trusted_end - horizon_days + 1`
   (`Config.latest_trusted_snapshot()`, = 2025-05-02 for a 30-day horizon). 2025-06..2026-09-05 is the
   "degraded" era: data is kept, never trained or evaluated on.
2. BigQuery plan: full detail targets the 24 trusted months 2023-06..2025-05. The Phase 2 default of
   "most recent 24 months" is superseded.
3. `ingest.sources` is an ordered config list `[opendigger, gharchive]`; each hour's manifest row records
   `source_host`, `expected_events`, `expected_sha256`, `integrity`. Rows from OpenDigger carry
   `source = 'opendigger'` (events and push_daily) so they can be excluded from any public publish.
4. The GitHub API is a cross-check, not the discovery source: daily, for the top-200 candidates, store
   `api_stars_7d` next to event-based `stars_7d`, show the ratio on the status page, alert when the
   median ratio drops below 0.8. Realized outcomes on the live track record use API-verified stars.
   Methodology page must say: live labels use API stars; historical labels use GH Archive in the
   trusted era.
**Findings that qualify the decision (reported to the human, not silently changed):**
- Measured degradation onset is 2025-05-24, eight days before `trusted_end`. May 24-31 runs at 0.60-0.73
  of baseline. The configured value follows the human decision; moving it to 2025-05-23 is a one-line
  change (`latest_trusted_snapshot` would become 2025-04-24).
- Full mode costs 10.5 TB scanned for the 24 trusted months vs 994 GB for spine over all history
  (`docs/bigquery_cost_plan.md`): about 12 sandbox quota months for detail via BigQuery alone, 16 when
  packed greedily after spine. Recommended: BigQuery for spine (two calendar months), hourly files from
  data.gharchive.org for detail (about 1.5 TB download, same parser as live). Awaiting approval; nothing
  beyond dry runs and the capture query has been run.
- OpenDigger: files exist from 2026-09-06 at 214-446 MB/hour (8x the events of gharchive.org per #323).
  The documented per-hour manifests (`...-H.manifest.json`) returned 404 for every hour probed (2026-09-06
  hours 0,1,2,12,23, and five later hours up to 2026-10-11), so integrity/gap checks are wired but
  inert: `ingest.sources[].manifest_keys` stays null until a real manifest is observed (field names are
  not guessed). Throughput from the developer machine was ~6 KB/s, versus ~4.5 MB/s for
  data.gharchive.org, which makes OpenDigger unusable from here and unverified from GitHub Actions.
  It is therefore configured but `enabled: false`; the switch is gated on `reports/source_validation.md`.
- License: the OpenDigger repository is Apache-2.0 "for the code part"; no license or terms were found
  for the mirrored data (host index page, #323, README). Per the decision, OpenDigger-sourced rows are
  not to be republished in the public Hugging Face dataset until the human answers.
- The configured `GH_ENRICH_TOKEN` (fine-grained, public read-only) cannot list stargazers (HTTP 403 on
  REST and GraphQL); a classic no-scope PAT, or `GITHUB_TOKEN` in Actions, is required. docs/HUMAN_SETUP.md
  step 4 is corrected.
**Consequences:**
- Train/serve skew risk: the model is trained on pre-2025-06 data, but live scoring reads post-2025-10-07
  payloads in which PR author, PR created time and merged flag are NULL (ADR-007). Tier-B features that
  use those fields must be excluded from the live model or trained with them masked; `era_post_2025_10`
  (ADR-003) is moot for training since no post-trim snapshot is ever trained on.
- Live features whose look-back reaches before 2026-09-06 (up to `daily.recent_window_days` = 160 days)
  read degraded GH Archive stars and are biased low until about 2027-02. The API cross-check ratio is the
  monitor for this; early live scores should be labelled "provisional".
- `PARSER_VERSION = 2`: staged push rows carry `source`. Existing staged/manifest data re-ingests.
- New code: `breakout.ingest.bq.{sql,survey,plan,report,capture}`, `breakout.ops.capture_quality`,
  `breakout.enrich.stargazers` (REST client keyed on repo id), `download_from_sources`.
