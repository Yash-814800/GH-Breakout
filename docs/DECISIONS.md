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

## ADR-010: Hourly-file backfill from 2023-06-01, trusted_end 2025-05-23, API-first constraints, live gate (2026-10-12)
**Context:** ADR-009 left four open questions; the human decided on 2026-10-12. Two facts changed the
design while implementing it: (1) GitHub restricted the stargazer-listing endpoints to repository
admins and collaborators in July 2026 (changelog 2026-06-30 "Upcoming access restrictions to public
API endpoints and UI views"; docs.github.com/en/rest/activity/starring), and (2) the BigQuery spine
range 2015-01..2023-05 is only 522 GB.
**Decisions (human):**
1. `GH_ENRICH_TOKEN` is a classic PAT with no scopes and a 1-year expiry, used locally and in Actions
   (not `GITHUB_TOKEN`). Rotation reminder in `docs/runbook.md`; HUMAN_SETUP step 4 corrected. Set up
   2026-10-12, expires 2027-10-12. (Verified: valid, `x-oauth-scopes` empty, 5,000 req/h.)
2. `history.trusted_end = 2025-05-23` inclusive (trusted data = `created_at < 2025-05-24`), matching the
   measured onset on 2025-05-24 (ADR-009). `Config.latest_trusted_snapshot()` = 2025-04-24 for a
   30-day horizon. The separate `degraded_end` key is removed: the degraded era is everything after
   `trusted_end` until `live.source_start` (null until a live source is approved).
3. Schedule: BigQuery spine only for 2015-01..2023-05 (dry run: **522.4 GB**, 101 months; with the
   55 GB already spent it is 578 GB of the 900 GB budget, so it fits this calendar month; awaiting
   approval to run). Everything from `history.cutover_date = 2023-06-01` comes from data.gharchive.org
   hourly files via the Phase 1 parser (`breakout backfill hourly`: trusted era first, then degraded;
   resumable; <= 4 concurrent downloads). `history.detail_start_date = 2023-06-01`. Four days that
   BigQuery lacks but hourly files have are listed in `history.hourly_gap_days` (2015-12-31,
   2021-05-08/10/11); five days exist in neither source (2020-08-22, 2021-08-26, 2021-10-26/27/28).
   A separate `live.source` / `live.source_start` pair (both null) holds any future live-source switch.
4. OpenDigger stays off by default and its rows (`source = 'opendigger'`) never go to the public HF
   dataset. `breakout lake verify` lists files that contain them.
5. Live-source gate (blocks Phase 9 scheduling): the source test returned NO-GO for OpenDigger (below); the API-first design note is not written, pending human review.
6. Every feature-dictionary entry declares `live_available`; the live champion trains only on those;
   the full-feature model is a research result in `reports/model_cv.md`. `breakout.features_dict`
   rejects `live_available: true` for features that read columns which are NULL in live payloads
   (PR author, PR created time, merged flag).
7. Provisional scores: a live feature or label window whose look-back overlaps days not from a
   trusted source (`Config.window_is_provisional`) is flagged `provisional`, shown as such on the
   leaderboard, and excluded from headline track-record metrics; the methodology page states why.
**Lake verify invariants (`breakout lake verify`, `breakout.lake.verify`):** `bq-` files only for months
entirely before the cutover; `day-` files only from the cutover (plus `hourly_gap_days`); rows lie
within the file's month/day; `bq` files carry only `source='bq'` and `detail_level=0` before
`detail_start_date`; hourly files carry `hourly`/`opendigger` and `detail_level=1`; `event_id` is
unique per event type and month across all files; `push_daily` unique on (repo_id, actor_id, day);
hive `event_type` agrees with the rows; OpenDigger files are enumerated.
**Consequences:**
- The stargazers API no longer provides `starred_at` for other people's repositories. This
  invalidates (a) the per-repo capture validation against API timestamps asked for in ADR-009,
  (b) the daily `api_stars_7d` cross-check as specified (it becomes a ratio of 7-day *count deltas*
  from daily `stargazerCount` snapshots, net of unstars), and (c) item 5(b) of the NO-GO design
  (starred_at for ~2,000 movers). Count snapshots (`stargazerCount` via GraphQL batches, search
  `stargazers_count`, REST `stargazers_count`) remain available.
- ADR-009's decisions 1 (`trusted_end`) and 2 (BigQuery plan) are superseded by this ADR; its
  findings and the remaining decisions stand.
- Backfill from hourly files is about 2 TB of download (trusted era ~1.5 TB, degraded era ~0.5 TB)
  and a few hundred GB of disk while staging is kept.
- Tier B features have no history before 2023-06-01; the first snapshot with a full 160-day detail
  look-back is 2023-11-08.

**Source test result (run 38194688025, US/Arizona Azure runner, 3 hours 2026-10-11 21-23 UTC):**
OpenDigger 8-11 KB/s sustained with 108-147 s to first byte (after 15 minutes only 1.7-2.6 % of a
367-440 MB hour was received); data.gharchive.org 54 MB/s for 14.7-14.9 MB hours. OpenDigger and
gharchive manifests: 0 of 48 hours exist. gharchive WatchEvents per hour: 169, 179, 213. Verdict:
NO-GO on the >= 1 MB/s criterion; the stargazer-timestamp capture criterion is not measurable
(stargazer lists restricted since July 2026). `reports/source_validation.md`.

## ADR-011: Hourly backfill runs in GitHub Actions, not on the laptop (2026-10-12)
**Context:** ADR-010 assumed `breakout backfill hourly` runs on the developer's laptop (~2 TB download,
~45 GB lake, ~80 GB staging). The human reported that Phase 1 ingestion previously crashed Claude Code
on the laptop and asked to keep heavy work off the machine.
**Decision (human, 2026-10-12):**
1. Do not run the hourly backfill locally. It moves to a GitHub Actions matrix workflow (one job per
   month of days, within the 14 GB runner disk and 6 h limit), built in Phase 3 together with the Hugging
   Face upload: each job parses its days with the Phase 1 parser, uploads the day files to HF, and
   discards staging.
2. The BigQuery spine extraction stays a local, one-time job (it needs ADC credentials; no service-account
   key is to be created). Its approval remains open; when approved it runs with `--workers 1` under a
   memory cap.
**Consequences:** ADR-010 item 3 "laptop" wording is superseded for the hourly path only. Phase 3 gains
an Actions backfill workflow and needs the `HF_TOKEN` Actions secret (human action). Backfill must be
resumable across jobs, so the hourly manifest has to live on HF (or be derived from the lake listing)
rather than only in `data/manifests/`. Local staging from Phase 1 (`data/staging`) can be deleted.

## ADR-012: Memory-bounded month finalization and SSD-hosted lake (2026-10-13)
**Context:** The developer machine has 15 GB RAM and Phase 1 had crashed Claude Code; the backfill had to
run under a hard cap. Month finalization failed with DuckDB OOM four times on 2022-10/12 data: a month
holds ~60 M PushEvent rows and ~10 M wide CreateEvent rows, and `DISTINCT ON (event_id) *` plus a second
global `ORDER BY` (or a long-lived connection, or a per-chunk `UNION ALL`) exceeded the cap even with
spilling. Local disk was also the limit (46 GB free for a ~57 GB lake).
**Decision:**
1. The backfill runs as `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=100%`
   with `--workers 1`. Every DuckDB statement runs on a fresh connection with `memory_limit=1500MB`,
   `threads=1` and a spill directory under `data/staging`.
2. Finalization is per day: dedupe on `event_id` for one day at a time into part files, then a sort-only
   pass (`repo_id, created_at, event_id`) for events, or a streaming concatenation in day order for
   `push_daily` (day, repo_id, actor_id). Peak RSS measured 1.0-1.9 GB. Output equals the earlier method;
   row order within `push_daily` month files is by day first.
3. Finalized month files are moved to the Lexar SSD (`/run/media/yash/Lexar SSD/gh-breakout/lake`) after a
   SHA-256 check and replaced by symlinks, so `data/lake` keeps the layout. This is capacity, not a backup:
   the SSD shares the physical disk with `/home`. Hugging Face (Phase 3) is the second copy.
**Consequences:** `data/lake` is readable only while the SSD is mounted. The merge code is slower than a
single global pass (about 3 min per large type per month). Tests cover the day-wise merge.

**Addendum (2026-10-13, human):** the Lexar SSD is the primary home for all local data. `data/` on the dev
machine is a symlink to `/run/media/yash/Lexar SSD/gh-breakout/data` (lake, manifests, staging, parity,
audit); no machine path is committed. `.gitignore` gained `/data` because `data/` does not match a
symlink. All 943 symlinked lake files and 272 real files were checksum-verified before the swap;
`breakout lake verify` passes through the new path. Consequence: nothing under `data/` is available
when the SSD is unmounted, and NTFS (fuseblk) is slower for small writes than btrfs.

## ADR-013: Dataset license MIT; lake size may exceed 60 GB; HF_TOKEN Actions secret (2026-10-13)
**Context:** Phase 3 needs a dataset-card license (HUMAN DECISION), the 60 GB lake target from ADR-001 is
exceeded once the hourly era is added (spine 57 GB + ~45 GB), and Actions needs the HF token.
**Decision (human):** (1) dataset cards declare `license: mit`; (2) exceeding the 60 GB target is accepted;
(3) `HF_TOKEN` is stored as the repository Actions secret (set 2026-10-13 with `gh secret set`;
`GH_ENRICH_TOKEN` already exists).
**Consequences:** The cards must state provenance (GH Archive, public GitHub events) and that the license
covers the repository's own processing and derived tables, and must not claim rights in the underlying
events or in names/logins they contain. HF storage is best-effort for public datasets; at ~100 GB the
upload must stay in batches and the daily job keeps appending compacted month files only. A `LICENSE`
file for the code still needs the copyright holder's name.

## ADR-014: Phase 3 starting constraints for the Hugging Face lake (2026-10-13)
**Context:** Handoff after Phase 2. These facts shape Phase 3 and are not in the phase file.
**Decision / facts:**
1. The Phase 3 plan must treat the SSD lake as the single source: `data/` is a symlink and is not a
   backup. No `bq-*` file is deleted locally until the same file is on HF and checksum-matched in the
   catalog; compaction deletes day files only after the HF commit succeeds (as in the phase file).
2. Per-file size: the largest `bq-*` files are below 500 MB; the 1 GB split rule is not hit for `bq`,
   but is still implemented for month files built from hourly days.
3. Commit batching: 943 `bq-*` files means at least 12 commits at 80 files; commit in month order
   with the catalog updated in the last commit of each batch. Uploads of ~57 GB run in the background,
   resumable (skip-if-sha-matches via the remote catalog), one worker, never in the foreground.
4. The hourly-era backfill is an Actions matrix that uploads per-month results to the events repo; it
   reads the hourly manifest from HF and writes it back, so concurrent jobs must not touch the same hours
   (one job = one month, jobs serialized per era, `concurrency` group).
5. Free HF storage is best-effort; the events repo is expected to reach ~100 GB. Mitigation if HF refuses
   or throttles: keep `bq` history in the repo and publish the hourly era as month files only.
**Consequences:** Phase 3 adds an Actions workflow (`hourly-backfill`) in addition to the phase file's
deliverables; PROGRESS "Handoff to Phase 3" lists what exists and what is missing.

## ADR-015: Phase 3 lake sync design (2026-10-15)
**Context:** Phase 3 implementation choices that differ from or extend the Phase 3 brief (kept locally).
**Decision:**
1. **Catalog in every commit.** Each upload commit carries the refreshed `catalog.parquet` and is
   guarded by `parent_commit`; a lost race re-reads the remote catalog and continues (already-committed
   files are skipped by sha256). Several Actions jobs can therefore push concurrently (`max-parallel: 2`).
2. **Resumability via the catalog, not a shared manifest.** The hourly manifest is not a single remote
   file: each month job writes `manifests/hourly/hourly-YYYYMM.parquet` (and `hourly-gap-days.parquet`),
   so concurrent jobs never write the same remote file; `lake pull --manifests` merges fragments locally.
   A month with `month-` files in the remote catalog is skipped.
3. **Day files are not pushed by `lake push` unless `--include-days`.** The 20 Phase 1 test days stay
   local; backfilled months arrive only as `month-` files (no day files ever exist remotely for them).
4. **Size cap is 1 GB per file (`lake.max_file_mb`), split on row-group boundaries**; `target_file_mb`
   is a sizing hint. A commit is also capped by bytes (`huggingface.max_bytes_per_commit`, 8 GB).
5. **Compaction** is a sort-only pass (`repo_id, created_at, event_id`) over per-day-deduplicated day
   files on a fresh DuckDB connection (1500 MB, 1 thread, spill to `data/staging`), with
   `hive_partitioning=false` (DuckDB otherwise adds `year`/`month` columns from the path).
   `push_daily` is a streaming concatenation in day order. The month is complete only when every hour
   has a manifest row that is `ok` or `missing`.
6. **Invariants added to `lake verify`:** schema/columns equal `schema.py`, `schema_version` equals
   `SCHEMA_VERSION` (stored as Parquet key-value metadata `breakout.schema_version`, inferred from the
   columns for older files), no day files in months that have a `bq`/`month` file except
   `history.hourly_gap_days`, never both `bq` and `month`; `--deep` adds the duplicate `event_id` scan;
   `--remote` cross-checks local catalog, remote catalog and the Hub listing (LFS sha256).
7. **Storage on the SSD.** `HF_HOME` defaults to `data/hf_home` (set before `huggingface_hub` is
   imported), scratch files go to `data/tmp`, and lake commands refuse to run when the lake root is
   missing (SSD unmounted).
**Consequences:** `config/project.yaml` gains `huggingface.max_bytes_per_commit` and `lake.max_file_mb`.
Gap days (2015-12-31, 2021-05-08/10/11) are published as `day-` files beside the `bq` month.

**Addendum (2026-10-15, bootstrap upload):** the first two upload attempts were OOM-killed at the 3 GB
cap within ~45 s: a single 8 GB / 73-file commit makes the Hub client chunk and hash many files at once.
`huggingface.max_bytes_per_commit` is now 1.5 GB and `create_commit` runs with `num_threads=1`. Peak RSS
was ~2.1 GB under the 3 GB cap; the 60.68 GB upload took 44 commits (~2 h at ~11 MB/s). Lesson: check
liveness with `systemctl --user is-active <scope>`, not `pgrep -f` (it matches its own shell).

**Addendum (2026-10-16, hourly-era backfill):** the Actions matrix (`hourly-backfill`, run 38680271855,
41 month jobs plus the gap-days job) completed with 0 failures, about 22 h wall clock at two months in
parallel (~65 min per month; gap days 21 min). Result on the Hub: 1,523 files, 114.91 GB,
5,592,548,999 rows; all 142 months 2015-01..2026-10 are covered for every table, no day/month overlaps,
no OpenDigger rows, schema_version 1 everywhere, catalog and Hub listing agree (sha256 and size).
2026-10 is published as day files (month not over). Hour statuses over the 42 manifest fragments: 29,662
ok, 2 missing (2025-06-12 17:00 and 18:00 UTC, 404 at data.gharchive.org). The hourly era added 54 GB
(estimate was 45 GB); the repo is above the ~100 GB ADR-014 expectation, so the HF best-effort storage
risk in ADR-013/014 item 5 now applies (mitigation unchanged: keep month files only, no day files for
finished months).

## ADR-016: Phase 4 plumbing: name history, actor-age sampling, config (2026-10-16)
**Context:** Phase 4 (phase brief, kept locally) needs a name <-> repo_id map for trending and
HN, a monotone actor-id -> account-age map, and shared HTTP/rate-limit code. The phase file says "all
`events` files"; the local lake has only the `bq` history, the hourly era lives on the Hub (ADR-015).
**Decision:**
1. **Name history is built from WatchEvent spine columns only** (`repo_id, repo_name, created_at`),
   2015-01..2026-10-14. A repo that has never been starred is not named by anything Phase 4 enriches
   (trending and HN entries are about starred repos), and WatchEvent is the smallest type. The human
   approved the pull of the hourly-era WatchEvent files (`lake pull --types WatchEvent --since
   2023-06-01`, 54 files, 4.6 GB, on the SSD under `data/lake`). Result: 46,495,707 (repo_id, name)
   pairs over 44,921,123 repos (1.35 GB parquet).
2. **Bounded-memory merge.** One global `GROUP BY (repo_id, repo_name)` OOMed at 1.3 GB, so month
   aggregates are merged per `repo_id % 32` bucket and one sort-only pass writes the file (ADR-012
   pattern). Month and bucket parts are cached in `data/staging/enrich/` keyed on file names + sizes, so
   reruns are incremental and byte-identical in content.
3. **`resolve_repo_ids(con, table, history)`** matches case-insensitively; interval-contains wins, then
   most recent holder before `as_of`; a name first seen *after* `as_of` stays NULL (the repo did not
   carry that name yet). Only history rows for the queried names are materialised (the full table is
   too big for a 1.5 GB limit).
4. **Actor-age sampling.** 20,000 WatchEvent rows are reservoir-sampled per month (seed 42), distinct
   ids pooled, and 3,000 ids are taken at evenly spaced ranks (always including min and max): real
   actor ids spaced by quantile. 2,832 of 3,000 resolved (168 x 404 = deleted accounts, skipped).
   Isotonic regression (`IsotonicRegression`, `out_of_bounds="clip"`) gives 2,832 breakpoints; lookups
   are ASOF steps (`actor_id >= breakpoint`), ids above the max breakpoint carry
   `est_is_extrapolated`. The hold-out fit uses a fixed seed and 10% of the samples.
5. **Config.** New `enrich:` section (`output_dir`, `hf_prefix`, `max_rps`, `graphql_batch_size`,
   `workers`, `meta_max_age_days`, target-window parameters, `actor_samples`, HN start and window);
   outputs live under `data/derived/enrich/` (git-ignored) and are uploaded to the derived repo under
   `enrich/` with `lake.hf.upload_files` (existing commit caps).
**Consequences:** `repo_name_history.parquet` is large (1.35 GB) for a lookup table; if the derived repo
size becomes a problem it can be restricted to repos with >= 2 stars without changing any consumer.
Repos starred only in the degraded era (after 2025-05-23) are named from the sparse post-collapse
stream, so name resolution for 2026 trending/HN entries is incomplete (see PROGRESS).

## ADR-017: Repo metadata is fetched by node id; allowed metadata features (2026-10-16)
**Context:** The phase file prescribes GraphQL `repository(owner, name)` aliases built from the latest
known name, `databaseId` verification, and a REST `/repositories/{id}` fallback for every miss. Measured
on a 100-repo sample of the target set: 23% of lookups are gone (deleted, private or blocked) and
renamed repos are common, so the fallback would be one REST call for roughly a quarter of 1.7 M repos
(about 400 k calls, > 100 h at 1 request/s and over the 5,000/h core limit). GraphQL latency is
3-5 s per 100-repo batch.
**Decision:**
1. **Primary path is `nodes(ids: [...])` with 100 legacy global node ids per request** (`base64(
   "010:Repository<repo_id>")`), keyed on the immutable `repo_id`, so renames and transfers resolve
   without any name. Verified live: 77 of 100 resolved, query cost 1 point, `databaseId` equals the
   requested id for every returned node. The code still checks `databaseId == repo_id`; a mismatch (never
   observed) goes to REST by id.
2. **Null node = `status='not_found'`, source `graphql`; the row is kept.** A 60-repo sample had 14
   nulls; REST `/repositories/{id}` returned 404 for 13 and 403 (blocked) for 1. The status therefore
   means "unresolvable now: deleted, private or blocked", not strictly "404".
3. **Target set** is computed with DuckDB on trusted-era WatchEvents (created_at < 2025-05-24): repos
   with >= `candidates.min_stars_14d` (5) stars in any 14-day window starting within 120 days of their
   first observed star. "First observed event" is the first star (the local lake has no other types for
   the hourly era). Left-censoring: repos first starred in 2015-01..2015-04 may be older than the
   window implies; this only widens the superset. Result: 1,684,571 repos, fetched newest cohort
   first. Daily Phase 9 runs pass explicit ids (`--repo-ids-file`).
4. **Throughput:** 5 concurrent batches (`enrich.workers`) behind one shared 1 request/s throttle (batch
   latency is 3-5 s, so 3 workers reached only ~55 repos/s); measured ~95 repos/s, ~4.5 h for 1.68 M repos.
   Resumable via shards and `--max-age-days` (default 30); SIGTERM flushes a shard and consolidates.
5. **Feature allow-list** (`enrichment_columns` in `config/feature_dictionary.yaml`, enforced by
   `tests/enrich/test_feature_allowlist.py`): model features are `created_at`, `is_fork` (fixed at
   creation) and the two documented slowly-varying exceptions `primary_language` and `owner_type`. The
   exceptions can change (language re-detection, user -> organization transfer) but rarely, and their
   current value is the best available proxy of the value at snapshot time; the evaluation reports
   per-year metrics so drift would show. Never features: stargazer count, description, topics,
   homepage, archived/mirror/template flags, license, fetch status.
**Consequences:** `not_found` repos have only `repo_id`, `status`, `fetched_at`; Phase 6 must treat
missing metadata as "unknown", not as "not a fork". `owner_created_at` is NULL for REST-sourced rows.

## ADR-018: Trending sources and robots.txt decision (2026-10-16)
**Context:** Phase 4.4 needs a trending history for the lead-time metric.
**Decision:**
1. **Sources (all MIT-licensed, verified in each repo/card):**
   - `hf_top_projects`: HF dataset `ronantakizawa/github-top-projects`, `full/data.csv`, license `mit`
     (card). Columns `name, star_count, fork_count, repo_owner, rank, date` (no language column: the
     all-languages page scraped from Wayback Machine snapshots). 423,098 raw rows, 2013-08-21 ..
     2025-11-30, 2,511 distinct days. Several snapshots can fall on one date, so `rank` is not unique
     within a date; its card documents uneven snapshot frequency (see `DATASET_ISSUES.md`).
   - `antonkomarev`: `antonkomarev/github-trending-archive` (MIT), daily JSON per language, ordered
     lists; `language: null` is the all-languages list; 2021-12-31 .. 2026-10-15 (all-languages lists
     from 2023-09-09).
   - `larsbijl`: `larsbijl/trending_archive` (MIT), daily markdown with per-language sections
     (python, go, rust, cpp, javascript, typescript and earlier coffeescript), 2014-08-09 ..
     2026-10-15, 4,237 days. Phase file candidate `antonkomarev/github-trending-archive` confirmed.
   - Sources are read from shallow git clones (one clone each, no per-file requests).
2. **Union** keyed on `(date, rank, repo_name, language_filter, source)`; `language_filter` is NULL for
   all-languages lists. The lead-time metric must use `language_filter IS NULL` rows (days listed in
   PROGRESS) or state otherwise.
3. **robots.txt (checked 2026-10-16):** `https://github.com/robots.txt` has no `Disallow` for
   `/trending` under `User-agent: *` (nor for the named AI agents); the file points automated users to
   the API. `trending-today` re-reads robots.txt on every run, fetches `/trending?since=daily` exactly
   once per day with the project user agent, and returns nothing (relying on the archives) if
   `/trending` is ever disallowed. HTML is parsed from `<article class="Box-row"><h2><a href=...>`;
   the live page returned 12 entries on the test run.
**Consequences:** A fetched-today row has `source='github_trending'` and is preserved across
`trending-history` rebuilds. The rank of `hf_top_projects` rows is best-effort.

## ADR-019: Hacker News points and comments are fetch-time values (2026-10-16)
**Context:** Algolia returns `points` and `num_comments` as of the fetch, not as of story time; using
them for a snapshot `D` would leak future popularity (CLAUDE.md section 5).
**Decision:**
1. Stories are the Algolia `search_by_date` hits for `query=github.com` restricted to the `url`
   attribute, `tags=story`, in adaptive windows (7 days, halved while `nbHits >= 1000`, minimum 1 h),
   1 request/s, resumable by window (`hn_windows.parquet`). 622 windows covered 2015-01-01 ..
   2026-10-16 (196,217 stories).
2. Allowed features: story **counts** with `created_at < D`; `points`/`num_comments` only for stories
   created before `D - 3 days` (most points accrue within 3 days), documented as an approximation in
   `config/feature_dictionary.yaml` (`enrichment_columns.hn_stories`). `hn-recent` refetches the last N
   days so values stay current; the history is a snapshot of the last fetch time (a story fetched once
   keeps its fetch-time points).
3. `url` is parsed to `owner/name` only for `github.com` / `www.github.com` repo URLs; reserved first
   path segments (orgs, topics, sponsors, marketplace, features, ...) and gist/raw/pages hosts are
   ignored. Names resolve with `resolve_repo_ids(name, story date)`.
**Consequences:** Phase 7 must implement the `D - 3 days` rule in SQL; there is no way to reconstruct
points at story time retroactively.

## ADR-020: Phase 5 dbt design: bucketed builds, candidate-first prefilter, local warehouse (2026-10-19)
**Context:** Phase 5 (phase brief, kept locally) as written is one `dbt build` over
the whole history. On this machine (15 GB RAM, 4 GB cgroup cap, DuckDB `memory_limit` 2 GB, 1 thread) five
design points of the phase file did not survive contact with 4.3 G events (3 failed full builds, ~25 h of
wall clock): single statements over the biggest tables OOM or spill past any sane cap; the NTFS (ntfs-3g)
SSD stalls or returns I/O errors under DuckDB's write pattern.
**Decision:**
1. **Hash-bucketed incremental models.** The models whose single statement does not fit are
   `incremental` with `unique_key='bucket'` (`delete+insert`) and are built one hash bucket per dbt call by
   `breakout build history` (macros `bucket_col`, `bucket_filter`; vars `bucket`, `n_buckets`; resumable:
   finished buckets are read from the table). Buckets of `repo_id`: `stg_stars`, `int_repo_star_daily`,
   `int_star_active_repos` (32), `int_active_repo_event_days` (4), `int_repo_daily_activity`,
   `int_contributor_sessions`, `int_stargazer_later_actions` (16). Buckets of `actor_id`:
   `int_actor_daily_activity`, `int_actor_cumulative_activity`, `int_star_events_enriched` (32). With
   `bucket` unset (small windows, the daily run) the same models build all buckets in one statement.
   `stg_bot_actor_signals` is incremental by month, built 3 months per call.
2. **`stg_stars` is a table, not a view** (deviation from "staging = views"): the first-star window needs
   a (repo, actor) pair's whole history and 477 M rows do not fit in one statement.
3. **Candidate-first prefilter** (new models): `int_star_active_repos` (>= `min_stars_14d` stars in a
   14-day window while at most `max_age_days + 2` days after the first star; 1.47 M repos) breaks the
   birth <-> young-moving cycle and bounds every wide scan. `int_active_repo_event_days` (non-bot events per
   repo-day of those repos) feeds birth and the mirror-like share; `int_early_stars` restricts stargazers to
   stars before `birth + max_age_days + 1 day` (the only stars a candidate at D can see; later stars only
   count towards labels via `int_repo_star_daily`). `int_repo_birth` is therefore defined over star-active
   repos, not all repos; `int_young_moving_repos` is 1,321,930 of them. `stg_bot_event_counts` moved to
   `int_bot_event_counts` and is restricted to the same repos (bot events exist on tens of millions of repos).
4. **Staging dedupe by construction, not by sort.** The lake guarantees one row per `event_id` across a
   month's files (`lake verify --deep`); the macro `lake_files` drops the locally kept Phase 1 `day-*`
   test-day files that sit beside a `month-`/`bq-` file and restricts files to the years of the window.
   Uniqueness tests on `event_id` run on the last 90 days of the window.
5. **Bot rule 3 (extreme non-star activity) is computed per month** (`stg_bot_actor_signals`: month x actor
   with > 1,000 events on a day). 59,586 bot actors (login pattern, seed, volume). Known false positives
   of the `-bot` suffix are accepted (human accounts named like `Forty-Bot`, a handful per million).
6. **`int_repo_birth`:** a PublicEvent counts as birth only if it is not after the first star (a repo
   starred before its PublicEvent was already public and has been re-published; this fixed 0.16% violations
   of `birth_not_after_first_star`). `is_left_censored` = no API date and first event within 30 days of
   `events_start`.
7. **Detail-dependent counts are NULL before `detail_start_date`** (2023-06-01), never 0
   (`int_repo_daily_activity`). `actor_repos_prior_90d` is a sum of daily distinct-repo counts (repo-days).
8. **Warehouse location and spill.** Writes by DuckDB to the NTFS SSD stalled (hung FUSE request for 7 h,
   one I/O error). The history build therefore runs with `GHB_WAREHOUSE` and `GHB_DUCKDB_TMP` on the local
   disk (`~/.cache/ghb-warehouse`, `~/.cache/ghb-duckdb-tmp`, spill capped by `GHB_DUCKDB_MAX_TEMP`) and the
   finished file is copied to `data/warehouse.duckdb` on the SSD. The lake stays on the SSD (read-only
   use is fine). `temp_directory` is a connection option (`config_options`), not a setting.
9. **Tests on huge tables are sampled:** `monotonic_cumulative` checks actors with `actor_id % 97 = 0`.
**Consequences:** `breakout build history` is the only supported way to build the whole history (resume
with the same command, `--resume-at a3` skips already built stages); a plain `dbt build` over the whole
window will OOM. The daily run (Phase 9) uses a short window and builds the same models without a bucket.
The warehouse is 33 GB; do not keep two copies on the 193 GB `/home` disk longer than needed.

## ADR-021: Phase 6 candidates, labels and evaluation design (2026-10-19)
**Context:** Phase 6 (phase brief, kept locally) left several details open.
**Decision:**
1. **Latest ingested day** (`latest_ingested_day` macro): the day of the newest star in `stg_stars` if that star
   is in hour 23, otherwise the day before; capped at `events_end - 1`. Snapshots run to that day + 1;
   `is_label_matured = D + horizon <= latest + 1`. With `trusted_end` 2025-05-23 the last matured snapshot is
   2025-04-21 (Monday; the exact limit 2025-04-24 is not a Monday).
2. **Candidates by cumulative sums + ASOF**, not window sums per (repo, D): one cumulative table per repo and
   four ASOF lookups (D, D-1, D-7, D-14) give all star windows. `mart_candidates` is incremental per `repo_id`
   bucket (unique key `bucket, snapshot_date`) so that live mode (`snapshot_dates_mode = single`) never
   deletes history rows. Mirror-like repos are always excluded; `exclude_forks` governs `is_fork`.
   `not_found` repos (unknown metadata) stay candidates (ADR-017). Bot owner = owner part of the name last
   seen before D matches the bot login pattern, the `known_bots` seed, bot logins from the bot-actor signals,
   or the metadata `owner_id` is a bot actor. Owners that are bots only by volume and have no known login are
   not caught.
3. **Labels** as specified. `first_trending_date` and `trending_covered` use only all-languages lists
   (`language_filter IS NULL`, ADR-018); `trending_covered` = at least 54 of the 60 days of the window have such
   a list (so most of 2014-2018 and 2019-07..12 count as not covered; the lead-time report rests on 2019-01..05 and 2020 onward).
   `days_to_threshold` is the first day offset where forward cumulative stars reach `threshold_rel`.
4. **Folds:** calendar blocks of `test_window_months`; first block starts on the first of the month on or after
   first snapshot + `min_train_years`; train = matured dates `<= test_start - embargo_days`; `make_folds`
   also requires the horizon and raises if `embargo_days < horizon_days`. Blocks may be shorter at the end.
5. **Metrics:** precision@k = hits / k; AP and recall@k only for snapshots with a positive; ties by `repo_id`.
   CIs: moving-block bootstrap (4 consecutive weekly snapshots) over snapshot dates, 1,000 resamples; the
   pooled PR-AUC CI reuses a once-sorted order with snapshot multiplicities as weights.
6. **Lead time** is measured against the repo's earliest observed Trending date in covered windows; a flag at
   or after the Trending date is not "early". Weekly resolution caps the precision of the lead.
7. **Dependencies:** `pandas` and `matplotlib` moved to runtime dependencies (already locked); mypy ignores
   pandas stubs.
**Consequences:** the baseline B1 is the bar for Phase 8: PR-AUC 0.0520, P@25 0.120 (pooled). Label rate is
0.51% by construction; every year is evaluated separately. Live scoring must call `mart_candidates` with
`snapshot_dates_mode: single` and a warehouse that contains the staging/intermediate tables of the daily window.

## ADR-022: Phase 7 feature design: tastemaker, groups, deviations from the phase file (2026-10-19)
**Context:** Phase 7 (phase brief, kept locally) specifies seven feature groups. Implementing them on the
real tables (`int_*` of Phase 5, `mart_candidates` of Phase 6) forced several definitions that the file leaves open or
that cannot be built as written.
**Decision:**
1. **Layout.** `dbt/models/features/`: `feat_<group>` (incremental, `unique_key=[bucket, snapshot_date]`, built per
   `repo_id` hash bucket, `on_schema_change: fail`) and `mart_repo_features` = `mart_candidates` keys LEFT JOIN all
   groups (`dbt_utils.star`). Every group also carries `_max_input_ts` (newest source timestamp used, test-only,
   not in the mart; `dbt/tests/features_no_future_inputs.sql` fails on any value `>= snapshot_date`). The mart has
   `bucket, repo_id, snapshot_date` plus 71 features, no name column, no calendar feature.
2. **`int_repo_daily_activity` gained `n_comment_events` and `n_pr_events`** (all-era totals per type). Without them
   `pr_events_14d`, `comment_events_14d` and the event-type entropy would be NULL before 2023-06-01 (the existing
   columns are detail-dependent). The table was rebuilt (16 buckets, same SQL otherwise).
3. **Tastemaker** (`int_actor_early_stars`, `int_actor_early_cum`, `int_repo_first_hit`, `int_tastemaker_thresholds`):
   an *early star* is a first star made while the repo had `< max_stars_total` stars (rank among its first stars) and
   was `<= max_age_days` old: the candidate universe. `is_hit` = the repo gains `>= absolute_min_gain` (500) first stars
   on the days `(star_day, star_day + 60]` (day granularity). `outcome_day = star_day + 60`; a consumer at D joins with
   `D > outcome_day` (an ASOF join, strictly), which is the day-granular form of `outcome_known_at < D` and is the
   conservative one. Score `(hits + alpha) / (early + alpha + beta)` with alpha 1, beta 50 (`features.tastemaker`).
   The monthly "top 1%" threshold is computed from `(early_known, hits_known)` state counts (running sum of +1/-1
   deltas per state) instead of scanning the actor table per month, and uses the last month boundary `<= D`.
   Ties at the threshold stay in the group (the threshold is the smallest score whose cumulative share reaches
   99%). Beta: the base hit rate of early stars (43,137,077 early stars with an observable outcome, 2,090,675 hits)
   is 4.85% (8.5% in 2015, 3.0% in 2023, 4.3% in 2025), so beta = 20 (prior mean 1/21 = 4.8%); alpha stays 1.
   `int_actor_early_stars` has 5,568,720 actors with an early star; the top-1% group is built from the 18.5 M
   actor states with >= 5 known early stars.
4. **Deviations from 7.1 (all documented in the dictionary):**
   - `distinct_actors_14d` -> `actor_days_14d` (sum of daily distinct non-bot actors; an exact distinct count over a
     window would need another pass over every event table); `issue_comments_14d` -> `comment_events_14d` (comments on
     issues and PRs together; the split is detail-only); `distinct_pushers_28d` is exact (from
     `int_core_actors_daily.pushed`).
   - Sessions: start-based counts use `session_start in [D-28, D)` (the start of a session depends only on earlier
     events). Duration, size and "top actor share" use only sessions complete as of D, i.e. `session_end + gap < D`
     (an event after D within the gap would have extended it). `new_contributors_28d` counts actors whose
     `session_id = 1` starts in the window (non-push activity), not `int_contributor_first_seen` (which includes push
     days). `top_actor_share_28d` is over contribution events, not all non-star events (actor-level push / fork
     counts are not materialised).
   - `owner_is_org` is not built: the staging models carry no `org_id`; `owner_type` (Tier C) says the same.
     `owner_prior_breakouts` uses `int_repo_first_hit` (an early star followed by 500 stars in 60 days, known before D).
   - Tier B NULL rule: a covered window with no event is 0, a window without any detail day is NULL;
     `detail_coverage_28d` = detail days / 28. `core_actor_count_90d` is NULL on and before `detail_start_date`.
     Merge features are NULL for windows that reach `features.payload_trim_date` (2025-10-07); `era_post_2025_10`
     and the merge features are `live_available: false` (constant 0 in training / flag removed in live payloads).
   - `primary_language`: a seed `top_languages` (the 30 most frequent languages among candidate repos) maps the rest
     to `Other`; NULL and not-found repos are `Unknown`.
5. **Dictionary** (`config/feature_dictionary.yaml`): the Phase 1 loader fields (`tier, description, requires,
   live_available`) plus the 7.3 fields (`group, dtype, unit, allowed, leakage_notes, explain_template{high,low}`);
   `sentence` of the Phase 1 example is replaced by `explain_template`. `validate(strict=True)` checks them; a unit
   test compares the dictionary with the columns of the mart in both directions.
**Consequences:** the training table (`mart_repo_features` + labels) is 71 features; the live champion's set is the
`live_available` subset (68). Detail features are research-only before 2023-11-08 (ADR-010).

## ADR-023: Phase 7 leakage defences and test design (2026-10-19)
**Context:** 7.2 asks for a time-travel test that rebuilds the features with all inputs truncated at D. A rebuild from
raw events of the 15-20 hour Phase 5 pipeline per test date is not practical, and sessions / tastemaker states have
look-ahead structure that needs care.
**Decision:**
1. **Time-travel test** (`breakout build leak-test --date D ... --sample 300`, `breakout.features.leak`): a
   deterministic sample of the candidates of D is copied (with everything the feature SQL reads for them: their
   stargazers' other early stars, their owners' repos) into two small DuckDB files, one complete and one cut at D
   (`time < D` on each table's own timestamp column; late first responses / closes / merges / reviews of issues and PRs
   become NULL; a session that straddles D ends one second before D). The tastemaker models are rebuilt inside the
   copies from the truncated early stars; only the month thresholds (they need every actor) are copied. The real dbt
   models run on both (`snapshot_dates_mode: single`, `events_end = D`) and every column of every sampled
   `(repo_id, D)` must be equal (floats within 1e-9). The complete copy is also compared with the real history mart
   (copy fidelity). Mutation check: changing `<` to `<=` in `feat_star_dynamics` or `>` to `>=` in the tastemaker ASOF
   join makes the test fail (done on the synthetic world, see tests).
   Limit: the derived columns of the materialised intermediates (`actor_events_prior_90d`, sessions, birth) are not
   rebuilt from raw events; they are covered by their own construction and the Phase 5 tests.
2. **Synthetic world** (`tests/features/synth.py`, `test_feature_models.py`): a tiny warehouse with the upstream
   tables, hand-computed expectations for every group (boundary days D-1/D/D+1, a hit that becomes known exactly on
   the day after `outcome_day`, sessions inside the gap, Tier B NULL vs 0, owner case-insensitivity), and the leak test
   itself. It found two real bugs while writing (NULL in an `avg` over a boolean, an ambiguous `USING`).
3. **Guard tests in dbt:** `features_no_future_inputs` (all rows, all groups), `features_star_windows_match_candidates`
   (the independent star windows equal Phase 6's), `features_tier_b_null_before_detail`, `features_row_parity`
   (one mart row per candidate), `features_stg_stars_bucket_layout` (the `bucket = repo_id % 32` pruning).
4. **Long builds run from a frozen copy of `dbt/`** (`GHB_DBT_DIR`): an edit of a model while a bucketed job is running
   aborted the next bucket (a seed referenced by a new model did not exist yet).
**Consequences:** `DBT_DIR` can be overridden by `GHB_DBT_DIR`; E501 is ignored in `src/breakout/features/` and
`tests/features/` (inline SQL).

## ADR-024: Phase 6 correction: repos with unknown metadata were silently dropped from the candidates (2026-10-19)
**Context:** Building the live single-date features (Phase 7) returned zero candidates for 2026-10-15. Cause: the
bot-owner filter of `mart_candidates` is `where not (regexp(...) or login in (...) or owner_id in (select actor_id
from stg_bot_actors))`. For a repo without metadata `owner_id` is NULL, so `owner_id in (...)` is NULL, the whole
predicate is NULL and the row is dropped. ADR-017/021 say the opposite ("`not_found` repos stay candidates, unknown is
not false"), and the Phase 6 checks did not catch it because 100% of the 861,799 candidate repos had metadata (the
23.5% `not_found` repos of the target set were exactly the ones removed). In the live daily run none of the new repos
has metadata yet, so the bug would have emptied the leaderboard.
**Decision:** `coalesce(owner_id in (...), false)` in `mart_candidates`; new dbt test `candidates_keep_unknown_metadata`
(fails when a candidate table over 1,000 rows has no candidate without metadata). `mart_candidates` and `mart_labels`
were rebuilt for the whole trusted history, the labels export and the baseline report were regenerated.
**Consequences (Phase 6 numbers change, the old ones were survivorship-biased):**
- Candidate-label rows 2,485,109 -> **3,098,574** (+24.7%), distinct repos 850,187 -> **1,125,113**, distinct positive
  repos 7,759 -> **9,606**, median candidates per snapshot 4,990.5 -> **5,626.5**, positive rate 0.510% -> 0.509%
  (by construction, 486 matured snapshots unchanged).
- Baseline B1 (7-day velocity), pooled over the 29 folds: PR-AUC 0.0520 [0.0491, 0.0551] -> **0.0286 [0.0246, 0.0345]**,
  ROC-AUC 0.821 -> 0.816, P@10 0.145 -> 0.129, P@25 0.120 -> **0.109 [0.100, 0.118]**, P@50 0.095 -> 0.086; B2 PR-AUC
  0.0405 -> 0.0197, B3 0.0447 -> 0.0227. The newly included repos (deleted / blocked accounts, largely spam and star
  farms) have high velocity and often do not stay: they are exactly what the fake-star detector (Phase 11) targets, and
  the bar for Phase 8 is this lower, honest baseline. B1 precision@25 by year is now 0.102 (2018), 0.116, 0.132,
  0.123, 0.143 (2022), **0.085 (2023), 0.055 (2024)**, 0.133 (2025, to April): in 2023-24, when the found share of the
  target repos is only 59-65%, velocity alone is a poor ranker. `reports/baseline.md` has the full tables.
- The Hugging Face copy `labels/candidates_labels.parquet` (derived repo) is still the old file until the human approves
  a new upload (`breakout build labels --no-build --upload`); the local export is current.
- Live scoring needs metadata for new candidates: `primary_language` / `owner_type` are 'Unknown' for every repo created
  after the trusted era until Phase 9 fetches them (`breakout enrich repos --repo-ids-file`); training contains a large
  'Unknown' share now (not_found repos), so the model sees the category.

## ADR-025: Phase 8 model design, evaluation and promotion (2026-10-19)
**Context:** Phase 8 (phase brief, kept locally) leaves compute, holdout and promotion details open. The
corrected B1 baseline (ADR-024) is the bar: pooled PR-AUC 0.0286, P@25 0.109. The laptop has 15 GB RAM and one worker
under a 4 GB cap (CLAUDE.md section 10).
**Decision:**
1. **Features:** `model_features(live_only=True)`: 68 allowed + live-available features (the research-only merge features and
   `era_post_2025_10` are out). `dataset.load_training` loads one year at a time (float32; a plain 3.1 M x 71 load peaked at
   4 GB and was OOM-killed). Keys / label columns as features raise an `AssertionError`.
2. **Negative subsampling (allowed by the phase file):** 10% of the negatives of the fitting rows, all positives
   (`model.negative_sample`). The inner-validation rows are never sampled, so early stopping (AP) and the calibrator see the real
   0.5% balance. Raw scores are therefore not probabilities (raw ECE 0.042); the calibrated ones are (ECE 0.0002 pooled OOF).
   Reason: 29 folds x 12 configs on 1.5-3 M rows would not finish on one thread; with sampling a fold takes 0.5-4 min.
3. **Inner split:** the last 3 months of a fold's training dates validate; fitting dates end `embargo_days` (30) before them.
   Search: 12 seeded configs drawn from the grid x `scale_pos_weight` {1, 3}, best inner-validation AP; the binned datasets are
   shared across configs (`feature_pre_filter=false`). Ablations use 3 configs and are compared with a 3-config run on all features
   (`abl_full_cheap`), not with the 12-config run.
4. **Calibration:** isotonic regression on the inner validation predictions (Platt when < 200 positives; never needed, all 29
   folds had >= 200), stored as JSON breakpoints (`np.interp`), clipped to [1e-6, 1].
5. **Monotone constraints** (`stars_7d`, `sg_share_experienced`) were run as a full variant: PR-AUC -0.0011, P@25 -0.003 vs
   unconstrained; rule "keep only if not worse" -> no constraints.
6. **Explanations:** the dictionary's `high` / `low` phrases are chosen by comparing the row's value with the training
   median, except for features whose `high` phrase describes a small value (`age_days`, `days_since_first_star`, every `hours`
   feature): those use the opposite comparison. Sentence = "Flagged because ..." (top 3 positive) + "Held back by: ..." (top 2
   negative). Missing values are skipped. The dictionary file was not edited (its hash is in the training manifest).
7. **Holdout and promotion:** holdout = the last `model.holdout_months` (6) of matured snapshots (2024-10-28 .. 2025-04-21,
   26 snapshots). An *evaluation model* trained only on dates before the holdout minus the embargo (same recipe) produces the
   holdout predictions used for the promotion rule (PR-AUC and mean P@25: both point differences > 0, neither paired CI entirely
   below 0; against B1 and, when there is one, the champion). The *shipped model* trains on the last 4 years minus the last 3
   months (validation / calibration) and is **not refit on all data**: the calibrator describes exactly that booster. Version =
   `YYYYMMDD-<git sha>`. A champion trained later than a candidate's holdout start has seen part of that holdout; Phase 9 must
   compare on a block neither has trained on.
8. **Locations:** packages in `data/models/<version>/` (+ `eval_model/`, `holdout_predictions.parquet`), `registry.json` beside
   them; uploaded to the models repo by `registry.upload_version` only with the human's approval.
9. **Daily check:** `mart_snapshot_dates` got a `range` mode (daily dates between `snapshot_start` and `snapshot_end`);
   `breakout ml daily-check --build` runs the history SQL for those days on a **copy** of the warehouse (the real marts keep
   weekly rows only) and scores them with the evaluation model.
**Consequences:**
- Tier A alone is as good as everything (abl_tier_A PR-AUC +0.006 [-0.001, +0.015] vs all features; P@25 +0.001): the
  detail (Tier B) and enrichment (Tier C) features add no measurable lift on the 2018-2025 CV. They stay in the model (they cost
  nothing and Tier B exists only from 2023); the claim of the phase file that they help is not supported by this data.
- The model's gain over B1 is large and present in every fold (PR-AUC 0.108 vs 0.029, P@25 0.241 vs 0.109) but most of it
  comes from recent-day velocity (`stars_1d`, `stars_3d`) that B1 ignores: a star-dynamics-only model reaches PR-AUC 0.064.
- `era_post_2025_10` cannot be evaluated: the trusted era ends before the payload trim.
- Live scoring after 2025-05-23 runs on degraded star capture (ADR-009) and with 'Unknown' metadata; the leaderboard
  probabilities are calibrated to the trusted era.

**Addendum (daily check result, 2026-10-19):** scoring 28 daily snapshots (2025-03-25..04-21) with the evaluation model:
precision@25 is similar on Mondays and other days (Monday minus other +0.032 [-0.008, +0.075]) but the calibration is
not: observed / expected positives are 0.90 on Mondays and 0.73 on the other days (the model over-predicts, more so on
non-Mondays; pooled daily ECE 0.0017). The booster and calibrator saw only Monday snapshots. **Phase 9 must not publish
daily probabilities from the Monday calibrator unchanged**: either train / calibrate on daily snapshots (the
`range` mode makes them) or apply a documented scale correction. Ranking quality is unaffected within the noise.

## ADR-026: Phase 9 daily pipeline, persistent state, and ops tooling (2026-10-20)
**Context:** Phase 9 (phase brief, kept locally) operationalizes daily inference, weekly retrain,
monthly maintenance, and health checks on free GitHub Actions runners ($0 cost, 2 vCPU / 7 GB RAM limit, no persistent
disk across runs). It requires persistent feature state on Hugging Face to avoid re-scanning 10 years of history on each
daily run, a training/serving parity test (§9.6), a tamper-evident prediction ledger, drift monitoring (PSI), and an
operational runbook.
**Decision:**
1. **Persistent State Architecture:** State tables (`tastemaker_state.parquet`, `owner_state.parquet`,
   `tastemaker_thresholds.parquet`) are maintained as of a cutover boundary (`2023-06-01`, the start of Tier B detail data)
   and synchronized with Hugging Face (`gh-breakout/gh-breakout-state`). Daily feature calculation uses the
   `use_persistent_state=True` mode in dbt (`feat_tastemaker.sql` and `feat_owner.sql`), joining the persistent base state
   with incremental activity in the window `[as_of, D)`.
2. **Training/Serving Parity Verification:** Parity was verified on Monday snapshot `2024-06-03` against the history
   warehouse mart. The staging copy uses candidate-filtered semi-joins (`repo_id in (select repo_id from mart_candidates)`)
   and sets DuckDB `max_memory = '3GB'` and `threads = 4`. Candidate Jaccard index reached 1.0000 (100%), overall cell
   match rate reached 99.99%, and prediction rank correlation (Spearman rho) reached 0.9999, with 100% of tested feature
   cells meeting parity requirements (reported in `docs/parity_daily_vs_history.md`).
3. **Tamper-Evident Prediction Ledger:** Each daily prediction batch is recorded in `ledger/predictions.csv` with a
   SHA-256 hash chain starting from genesis hash `0000000000000000000000000000000000000000000000000000000000000000`.
   The ledger is verified daily via `breakout ops verify-ledger` and committed to git to establish cryptographic proof of
   unmodified predictions.
4. **GitHub Actions Workflows:** Five workflows implement the automation schedule:
   - `daily.yml`: 07:00 UTC daily ingest, enrichment, candidate filtering, window features, champion scoring, ledger append,
     and static data export for GitHub Pages.
   - `weekly.yml`: Mondays 04:00 UTC champion re-evaluation, retraining candidate models, and promotion check.
   - `monthly.yml`: 1st of month 03:00 UTC persistent state update, threshold recalculation, and vacuuming.
   - `health.yml`: 08:30 UTC heartbeat monitoring, ledger integrity check, and feature drift calculation (PSI).
   - `backfill-day.yml`: Manual `workflow_dispatch` to repair or re-ingest a single target date.
5. **Feature Drift Monitoring:** Population Stability Index (PSI) is calculated daily on 14 key features against a
   reference baseline distribution (`reports/drift_report.json`), raising warnings at PSI > 0.10 and failure alerts at
   PSI > 0.25.
6. **Operations Runbook:** `docs/runbook.md` documents standard operating procedures for rerunning a failed day,
   recovering from multi-day gaps, rolling back models, and interpreting health check alerts.
**Consequences:**
- The daily pipeline runs well within GitHub Actions limits (~15 minutes total runtime) at $0 cost.
- Training/serving feature parity guarantees zero silent feature skew between offline model training and online serving.
- State tables must be preserved on Hugging Face; any corruption or schema change requires regenerating the state base
  using `breakout build state`.

## ADR-027: Phase 9 clean-runner correction (2026-10-20)

**Context:** ADR-026 and `PROGRESS.md` marked Phase 9 done after local checks only. The first `workflow_dispatch` of
`daily.yml` failed (run 39423153746) because a GitHub Actions runner starts empty and the orchestrator assumed the
dev machine's local state. The persistent state tables and the champion model were also never on Hugging Face (only on
the SSD), and CI had been red since Phase 5 because the tests need `dbt deps`.

**Decision:**
1. `breakout.daily.bootstrap` runs as step 0: `dbt deps`, merged hourly manifest fragments, the window's event files
   (including `push_daily`), the `enrich/` tables, live features, state tables and the champion. The daily run now pushes
   per-month manifest fragments (`manifests/hourly/hourly-YYYYMM.parquet`) and the day's live features
   (`derived/live/features/date=D.parquet`).
2. Seeds and staging/intermediate models are built before the state increment (step 5), not in step 8.
3. A failed run no longer refreshes `last_success_at` in the heartbeat.
4. `weekly.yml` pulls training rows, labels, live features and the registry first, and `ml promote --upload` pushes the
   candidate, champion and `registry.json` to the models repo (the registry is not committed to git).
5. `monthly.yml` is reduced to `lake verify-remote`. The actor-age top-up and repo metadata refresh sample the local lake
   or need live candidate ids and could overwrite full HF tables with partial ones, so they stay manual.
6. `health.yml` creates its `pipeline-health` label; `drift.find_recent_live_features` parsed the date from the wrong path
   component and never matched a file.

**Known gap:** daily step 7 (live enrichment: repo metadata, trending, HN) is not wired. Metadata features are
Unknown/NULL for new repos; wiring it needs a two-phase build (candidates, fetch metadata, features).

**Consequences:** the daily run takes ~3.5 minutes on a runner; the weekly retrain ~10 minutes. The state tables on HF
are as of 2023-06-01 plus the daily increments; they must not be deleted.

## ADR-028: Phase 10 website architecture: Astro static site, DuckDB-WASM, and GitHub Pages deployment (2026-10-20)

**Context:** Phase 10 requires an honest, zero-cost public website displaying the daily breakout leaderboard, repo detail pages, public track record, historical time machine, in-browser SQL explorer, methodology docs, and pipeline observability.

**Decision:**
1. **Framework & Static Generation:** Astro with `output: 'static'` hosted on GitHub Pages (`/<repo-name>/` base path). Configured via `astro.config.mjs` with `site: 'https://yash-814800.github.io'` and `base: '/GH-Breakout'` (driven by `SITE_URL` and `BASE_PATH` environment variables). All internal links and asset references use `import.meta.env.BASE_URL`.
2. **Base-Path Verification:** Build-time script `site/scripts/check-base-paths.mjs` verifies every HTML file in `site/dist/` to prevent any un-prefixed absolute URLs (`href="/` or `src="/`) from breaking on project pages.
3. **Pre-computed Site Data (`site/public/data/`):** Generated by `breakout publish site-data` prior to build time. Includes `leaderboard.json`, `repos/<repo_id>.json`, `track_record.json`, `backtest.json`, `status.json`, `meta.json`, `explorer/live_predictions.parquet`, and `explorer/oof_top100.parquet`.
4. **Schema Enforcement & Opt-Out:** Every exported JSON document is validated against Draft-07 JSON Schemas in `site/schemas/`. Repositories listed in `config/hidden_repos.yaml` are filtered from all public site outputs.
5. **In-Browser DuckDB-WASM:** `@duckdb/duckdb-wasm` loads lazily on `/explore/` and `/backtest/`, registering same-origin Parquet files (`oof_top100.parquet` and `live_predictions.parquet`). Verified support for HTTP 206 Partial Content range requests, with automatic fallback to buffer registration.
6. **Workflows & Hosting:** `daily.yml` pipeline uploads site data as an artifact, uploads to the Hugging Face derived repo under `site_data/latest/`, and deploys to GitHub Pages via `actions/deploy-pages`. `site.yml` deploys on push touching `site/**` or `docs/model_card.md` by pulling `site_data/latest/` from Hugging Face. `ci.yml` validates `npm run build` using committed fixture data in `site/test-data/`.

**Consequences:**
- The website deploys automatically on every daily run and repository push for $0 total cost.
- Leaderboard page size is ~185 KB raw (~35 KB gzipped), with Lighthouse Performance 100 and Accessibility 96.
- The SQL explorer operates entirely client-side without a backend database server.


## ADR-029: Leaderboard shows GitHub-API star totals; event counts are labelled as partial (2026-10-20)
**Context:** The first deployed leaderboard showed ranks 1-2 as `repo_id=...` (no stored metadata, non-existent links), and ranks 3-4
with 6 and 15 "observed" stars although GitHub reports 7,696 and 8,018. Cause: GH Archive star capture is degraded since 2025-05-24
(ADR-009), so `stars_total_observed`, `stars_7d` and the sparkline (all event-based) understate real growth, and the metadata file
lacked brand-new repos. The model's own features and the "Flagged because" explanation remain event-based (unchanged).
**Decision:** `breakout publish site-data` asks the GitHub API (GraphQL batch, `GH_ENRICH_TOKEN`) for the shown repos: current
`nameWithOwner`, language, description, creation date and `stargazerCount`. These are display-only and never features (CLAUDE.md section 6).
`stars_total_observed` now holds the API count (`stars_total_source = github_api`; falls back to `gh_archive` without a token).
Repos GitHub reports gone or blocked are dropped and the board is refilled from the next candidates. Daily counts are stored in
`star_snapshots.json` (45 days, restored from the Hub bundle on a clean runner) and give `stars_gain_api` / `stars_gain_days`, the
real gain over up to 7 days (null on a repo's first day). The captured-stars sparkline is drawn only when it covers at least half
of the real total.
**Consequences:** the gain column is empty on the first day and fills in from the second daily run. The explanation text still quotes
event-based numbers, which are what the model saw; the page says so. Ledger rows and model scores are untouched.

## ADR-030: Phase 11 suspicious-growth detector, similar repos, cohort retention, and insights (2026-10-21)

**Context:** Phase 11 (phase brief, kept locally) implements game-resistance and deep repository analysis:
1. A transparent, non-accusatory suspicious-growth score protecting the leaderboard from farmed stars.
2. Item-item co-star similarity ("People who starred this also starred...").
3. Stargazer cohort retention benchmarks comparing new repos against past breakouts.
4. A static `/insights/` page highlighting four core data stories with reproducible DuckDB SQL.

**Decision:**
1. **Suspicious-Growth Detector Architecture (`src/breakout/detect/`, `mart_suspicion`):**
   - **Six Core Signals:** Computed over candidate first stars in `[D-14, D)`:
     - `s_new_accounts`: Share of stargazers with estimated account age < 30 days (and < 7 days).
     - `s_inactive`: Share of stargazers with 0 events in the 90 days prior to starring.
     - `s_bulk`: Share of stargazers starring $\ge 50$ repositories on that UTC day.
     - `s_burst`: Maximum single-hour star share and inter-arrival coefficient of variation (regularity).
     - `s_lockstep`: Share of stargazers co-starring $\ge 3$ of the same repositories within $\pm 24$ hours (capped at 5,000 recent stargazers).
     - `s_no_engagement`: $1 - \min(1, \text{engagement} / (0.05 \times \text{stars}_{14d}))$.
   - **Scoring & Calibration:** Robust z-score per signal: $(x - \text{med}) / (1.4826 \times \text{MAD})$, with fallback to interquartile range or zero for degenerate zero-MAD distributions, clipped to $[0, 6]$. Signals combined with equal weights ($1/6$ each) into a raw score and mapped to $[0, 100]$ via the empirical CDF of historical scores.
   - **Classification & Reason Codes:** Low (< 90), Medium (90–98), High ($\ge 98$). Up to 3 factual, non-accusatory reason codes emitted per flagged repo.
   - **Display-Side Only:** `suspicion_score` is strictly display-side and is **never** fed as a feature into the LightGBM model.
   - **Neutrality & Maintainer Recourse:** Leaderboard presents a neutral `⚠️ Unusual pattern` badge with a reasons tooltip and a toggle checkbox to "Hide unusual star patterns". The `/about/` page outlines audit methodology and links to `.github/ISSUE_TEMPLATE/review-request.md` for maintainer review requests.

2. **Academic Validation & Relabeling Ablation (`reports/suspicion.md`):**
   - Ground truth comparison performed against the StarScout academic dataset (He et al., ICSE 2026, Socket Inc. / CMU / NC State, Apache 2.0 license).
   - Out of 15,773 historical `breakout_rel` positives from 2016–2025, only **81 (0.51%)** exhibited high suspicion.
   - Retraining ablation: relabeling high-suspicion positives as negatives yields negligible change on holdout PR-AUC (0.1407 vs 0.1396) and P@25 (0.3338 vs 0.3200).
   - **Decision:** Keep the training label definition unchanged to avoid label corruption from heuristic detectors; display suspicion score as a display-side audit indicator.

3. **Item-Item Co-star Similarity (`mart_similar_repos`, `similarity.py`):**
   - **Weekly Reference Index:** Precomputed in weekly workflow over repositories with $\ge 50$ stars in the past 365 days, retaining up to 2,000 most recent stargazers (excluding bots and bulk starrers). Optimized using DuckDB native `COPY (...) TO ... (FORMAT PARQUET, COMPRESSION ZSTD)`: indexes 80,965 repositories (17,251,385 stargazer pairs) in **71.7s**, producing a **90.9 MB** `reference_stargazers.parquet` and **471 KB** `reference_repo_sizes.parquet`.
   - **Daily Candidate Lookup:** Candidate stargazers joined on `actor_id` directly against `reference_stargazers.parquet` (with fast fallback to `int_early_stars` for young repos), computing cosine similarity $\text{overlap} / \sqrt{n_a \times n_b}$. Returns top 5 similar repos with $\text{overlap} \ge 5$ and $\text{cosine} \in (0, 1]$, excluding self and forks.

4. **Stargazer Cohort Retention (`cohorts.py`):**
   - Historical benchmark: precomputes median and IQR downstream engagement rates (forks, issues, PRs, comments within 30 days) across repo age buckets for historical `breakout_rel` positives, stored in `derived/reference/retention_reference.parquet` (4 rows, 0.15s build time).
   - Repo detail pages render a cohort retention heatmap matrix (cohort week $\times$ action type) benchmarked against historical median bands.

5. **Insights Page (`site/src/pages/insights.astro`, `publish/insights.py`):**
   - Published via `breakout publish insights` to `site/public/data/insights.json` (and `site/test-data/insights.json`).
   - Four data stories featuring narrative text, Observable Plot visualizations, and collapsible DuckDB SQL queries:
     1. Stars vs. Real Adoption: downstream engagement of breakout vs. other candidates' stargazers (breakouts retain slightly less, 8.0% vs 8.8% at 90 days).
     2. The AI-Era Shift: Proportion of breakout repositories classified as AI/ML/LLM tooling (2016–2025).
     3. Lead Time Distribution: Backtest early flag detection advantage relative to GitHub Trending.
     4. Unusual Star Patterns Over Time: Longitudinal prevalence of high-suspicion candidate repositories.

**Consequences:**
- Leaderboard maintains high integrity without silencing genuine viral repositories.
- Weekly reference indexing fits well within GitHub Actions execution budgets (~1.2 min runtime, ~91 MB artifact).
- Static export bundle size remains lightweight while delivering rich interactive visualizations.



## ADR-031: Phase 14 front-end redesign: design system, QA suite and deploy gate (2026-10-21)

**Context:** The Phase 10 site had page-level overflow at 375 px, raw floats and ISO timestamps on screen, hand-typed metrics (two wrong), a system-font stack and no shared layouts or tests
(`reports/design/audit_before.md`). Phase 14 asks for one cohesive design and automated proof of it.

**Decision:**
1. **Design system.** Tokens in `site/src/styles/tokens.css` are the only place with color literals; light and dark are token swaps. Tailwind v4 with its default palette disabled; all numbers, dates and
   text go through `src/lib/format.ts`; data is loaded and validated with zod (`src/lib/data.ts`), so a malformed file fails the build naming the file and field.
2. **Signature element.** The signal column (large condensed percentage plus a 28-day momentum strip, server-rendered SVG) is the same component on the leaderboard, backtest, digest and repo pages.
3. **Self-hosting.** Fonts and DuckDB-WASM come from the site itself. The remaining third-party request is DuckDB fetching its Parquet extension at runtime (no cookies, no user data).
4. **QA as code.** Playwright specs for layout (four widths), content (no raw values), axe (light and dark) and visual snapshots made in a pinned container; token lint; base-path and link checks; Lighthouse CI with the
   budgets from the phase file. All run in the `site-qa` CI job.
5. **Deploy gate.** The daily deploy runs the content check on real data before publishing. If it fails, the deploy is skipped, yesterday's site stays, and a warning is logged.
6. **Numbers come from reports, not text.** The methodology table reads `reports/metrics/*.json` at build time; the track-record sentence is generated in `breakout publish site-data`.
7. **Exporter changes** are limited to what the phase file allows: `owner_id` and `owner_type`, plus the track-record headline.
8. Deviations and their reasons are listed in `reports/design/decisions.md`.

**Consequences:** Visual changes now show up as snapshot diffs (regenerate with the `update-visual-snapshots` workflow). The dist folder is about 45 MB because of the DuckDB-WASM binary, well under the Pages limit. Phase 12
(feeds, badges, digest data) fills layouts that already exist. Four data problems found in earlier phases are listed in `docs/PROGRESS.md`.

**Amendment (2026-10-21, Phase 11 acceptance review):**
- The first insight texts were hand-written and contradicted their charts (story 1 claimed higher retention for breakouts, story 4 claimed a recent rise and used "star farming" wording, story 3 claimed a median lead of 1-2 days). The summaries are now generated from the chart data by `_summary_*` in `publish/insights.py`, titles are neutral, and story 3 states that it measures candidacy, not the model's ranking.
- The label policy after the ablation (keep labels unchanged) was marked HUMAN DECISION in the phase file and was chosen by the agent. It stays the working default until the human confirms or changes it.
- The story 4 SQL uses five of the six signals (no lockstep), so its prevalence differs slightly from `mart_suspicion`; the text says so.



## ADR-032: Phase 12 and 13 design: distribution, dbt docs, benchmark, no Bluesky bot (2026-10-21)

**Context:** Phases 12 and 13 (phase brief, kept locally) were implemented together on the owner's instruction, "everything except the Bluesky bot".

**Decision:**
1. **Bluesky bot (12.4) is not built.** `optional.bluesky_enabled` stays `false`; no `atproto` dependency, no posting code. The Mastodon variant is documented only (runbook). This is a deliberate deviation from the phase file.
2. **Feeds, badges, digest are derived from frozen snapshots** (`breakout.publish.distribution`), restored read-only from the snapshots repo on a clean runner. Feed items persist across runs through the `site_data/latest/feed_items.json` bundle (their age and star facts are captured on the entry day). `/feed.xml`, `/feed.json` and `/digest/feed.xml` are Astro endpoints; the GUID is `repo_id:first_flag_date` (`isPermaLink="false"`, written through `customData` because `@astrojs/rss` derives the GUID from the link).
3. **First snapshot is not "new".** The first live list has no history, so for the digest its repos are not counted as new (the feed still lists them as the initial entries).
4. **Badges** are written to `site/public/badges/` (git-ignored, regenerated daily and by `site.yml`); `by-name` files are lower case; badges never encode suspicion.
5. **Digests** live on the derived repo (`digests/`); `publish site-data` pulls them. `site.yml` no longer copies the fixture data under the real data (fixture digests and feed items would otherwise have been published); fixtures are only the fallback when the Hub pull fails.
6. **Discussions (12.5):** implemented and enabled by the owner. GitHub has no API to create a discussion category, so the post goes to **Announcements** until the owner creates a category named **Digest** in the repository settings. Posts are idempotent by title.
7. **dbt docs:** generated with `--empty-catalog` against an empty scratch lake and warehouse (compiling otherwise lists thousands of lake files and opens the 33 GB warehouse); column types come from `reports/dbt/catalog.json`, written from the warehouse's information schema by `--refresh-catalog`. The generic test `birth_not_after_first_star` only runs its logging query during `test`/`build`. Every model column has a description (new pytest check); `docs/data_dictionary.md` is generated and CI fails when it is stale.
8. **Benchmark:** clickhouse-local LTS 26.8.32.14 and DuckDB 1.5.6, 2022 data, 4 threads, 4 GB engine limit; queries that failed at 4 GB are repeated at a larger limit and both results are reported.
9. **Housekeeping:** code license **MIT** (owner's decision), `SECURITY.md`, `CITATION.cff`, `CONTRIBUTING.md`, bug issue template, Dependabot for uv, npm and Actions, third-party actions pinned to commit SHAs.

**Consequences:** the site gains `/blog/`, `/dbt-docs/`, feeds and badge snippets; `daily.yml` builds the badges and the dbt docs and passes them to the deploy job as artifacts. A re-run of the daily workflow for an already frozen date first reported a freeze conflict (the regenerated file is not byte-identical) and set the heartbeat to unhealthy; amended the same day: the run now keeps the frozen snapshot, publishes from it and stays healthy (`adopt_frozen_snapshot`).
