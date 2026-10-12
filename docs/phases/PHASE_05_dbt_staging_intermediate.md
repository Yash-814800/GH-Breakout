# Phase 05 — dbt project: sources, staging, intermediate models, tests

## Goal
Model the lake with dbt-duckdb in clean layers — showcasing window functions, sessionization,
cohort retention and data-quality testing — and produce the intermediate tables the feature
marts (Phase 7) and labels (Phase 6) are built from. The **same dbt project** runs for the full
history (laptop) and for the daily window (Actions), controlled by vars.

## Prerequisites
- Phases 03 and 04 done. Lake (at least the fast-start slice) available locally via `lake pull`
  or already on disk; `data/derived/enrich/*.parquet` present.

## Setup deliverables
1. Add deps: `dbt-core`, `dbt-duckdb` (latest stable, compatible pair).
2. `dbt/dbt_project.yml` (project name `breakout`), `dbt/profiles.yml` committed (no secrets):
   ```yaml
   breakout:
     target: local
     outputs:
       local:
         type: duckdb
         path: "{{ env_var('GHB_WAREHOUSE', '../data/warehouse.duckdb') }}"
         threads: 4
         extensions: [httpfs, parquet]
         settings:
           memory_limit: "{{ env_var('GHB_DUCKDB_MEMORY', '10GB') }}"
           preserve_insertion_order: false
           temp_directory: "{{ env_var('GHB_DUCKDB_TMP', '../data/tmp') }}"
   ```
   Always run dbt with `DBT_PROFILES_DIR=dbt` from the repo root via the CLI wrapper
   `breakout build dbt -- <dbt args>` which sets env vars (`GHB_LAKE`, `GHB_DERIVED`, `GHB_WAREHOUSE`)
   to absolute paths. Add `dbt/target`, `dbt/logs`, `dbt/dbt_packages` to `.gitignore`.
3. Packages: `dbt-labs/dbt_utils` (and `calogica/dbt_expectations` or `metaplane/dbt_expectations`
   — check which is maintained now). Pin versions in `packages.yml`.
4. Vars (in `dbt_project.yml`, overridable with `--vars`):
   - `events_start` (date, default `2015-01-01`), `events_end` (date, exclusive, default far future)
   - `snapshot_dates_mode`: `weekly_history` | `single` (used in Phase 7)
   - `snapshot_date` (used when mode = single)
   - `min_stars_14d`, `max_age_days`, `session_gap_minutes` — default from `config/project.yaml`
     (the CLI wrapper passes them so YAML stays the single source of truth).
5. Sources (`models/staging/_sources.yml`) using dbt-duckdb `external_location`:
   ```yaml
   sources:
     - name: lake
       meta:
         external_location: >-
           read_parquet('{{ env_var("GHB_LAKE") }}/events/event_type={name}/**/*.parquet',
                        hive_partitioning = true, union_by_name = true)
       tables:
         - name: WatchEvent
           loaded_at_field: created_at
           freshness: {warn_after: {count: 36, period: hour}, error_after: {count: 72, period: hour}}
         - name: ForkEvent
         # ... one per raw type
     - name: lake_push
       tables:
         - name: push_daily
           meta:
             external_location: "read_parquet('{{ env_var(\"GHB_LAKE\") }}/push_daily/**/*.parquet', hive_partitioning = true)"
     - name: enrich
       tables: [repo_metadata, repo_name_history, actor_id_age_map, trending, hn_stories]  # each with external_location to GHB_DERIVED/enrich/<name>.parquet
   ```
   Verify the `{name}` substitution works in your dbt-duckdb version; if not, set `external_location`
   per table. Freshness is only enforced in the daily run (`dbt source freshness` step in Phase 9).
6. Seeds: `dbt/seeds/known_bots.csv` (columns `login,reason`) with common automation accounts
   (dependabot[bot], renovate[bot], github-actions[bot], pre-commit-ci[bot], codecov[bot], netlify[bot],
   vercel[bot], allcontributors[bot], imgbot[bot], greenkeeper[bot], snyk-bot, dependabot-preview[bot],
   mergify[bot], stale[bot], sonarcloud[bot], coderabbitai[bot], copilot-swe-agent etc. — verify names from
   the data: query top logins ending in `[bot]` or `-bot` and review). Keep it small and documented.

## Models

Every model gets a YAML entry with a description, column descriptions, and tests. Use CTEs, explicit
column lists (no `SELECT *` from sources), and filter `created_at >= var('events_start') AND
created_at < var('events_end')` at the staging layer so every run is window-bounded.

### Staging (`models/staging/`, materialized as views)
- `stg_bot_actors` — actor_ids considered automation: login matches `\[bot\]$` or `-bot$`/`_bot$`
  (verify false positives), or in `known_bots` seed, or extreme **non-star** activity
  (> 1,000 events in a UTC day on ≥ 3 distinct days within the window). Columns: `actor_id, reason`.
  **Do not** classify heavy starrers as bots here — suspicious starring is a signal for Phase 11.
- One model per raw type, each: dedupe by `event_id`; cast types; add `actor_is_bot` via left join to
  `stg_bot_actors`; **exclude bot rows** (`where not actor_is_bot`), and keep a separate
  `stg_bot_event_counts` (repo_id, day, n_bot_events) for mirror/bot-heavy repo detection.
  - `stg_stars` (WatchEvent): **first star per (repo_id, actor_id)** only (`QUALIFY row_number() over
    (partition by repo_id, actor_id order by created_at, event_id) = 1`). Columns
    `repo_id, actor_id, starred_at, event_id`. Note in the docs: restars are dropped; unstars are invisible.
  - `stg_forks` (`forkee_repo_id`), `stg_issues` (action, number, target_user_id, target_created_at),
    `stg_issue_comments` (number, is_pull_request, target_user_id), `stg_pull_requests` (action, number,
    pr_merged, target_user_id, target_created_at), `stg_pr_reviews` (number, review_state),
    `stg_releases` (action, release_prerelease), `stg_creates` (ref_type), `stg_public_events`,
    `stg_push_daily`.
  - Detail columns are NULL where `detail_level = 0`; carry `detail_level` through.
- `stg_repo_metadata`, `stg_repo_name_history`, `stg_actor_age_map`, `stg_trending`, `stg_hn_stories`
  — light renames/casts over enrichment.

### Intermediate (`models/intermediate/`, materialized as tables; switch the big ones to
`materialized='external'` with `location` under `GHB_DERIVED/intermediate/<model>/` and
`partition_by` year if the DuckDB file grows past ~30 GB)
1. `int_repo_birth` — grain `repo_id`. `first_event_at`, `first_star_at`,
   `created_repo_event_at` (CreateEvent ref_type='repository', detail only), `made_public_at`
   (first PublicEvent), `api_created_at` (metadata), and
   `birth_at = CASE WHEN made_public_at IS NOT NULL AND made_public_at > COALESCE(api_created_at, created_repo_event_at, first_event_at) THEN made_public_at
                    ELSE COALESCE(api_created_at, created_repo_event_at, first_event_at) END`.
   Also `birth_source`, `is_fork` (metadata `is_fork` OR repo_id appears as any `forkee_repo_id`),
   `is_mirror_like` (metadata `is_mirror` OR bot events > 80% of events in its first 30 days).
   **Caveat to document:** `first_event_at` is left-censored at the history start (2015-01-01);
   repos born earlier must not look "young" — exclude repos whose `first_event_at` is within 30 days
   after the history start unless `api_created_at` proves they are young.
2. `int_repo_star_daily` — grain `(repo_id, day)` over **all repos**: `n_stars`. This is the only
   all-repo daily table (stars are needed to define candidates).
3. `int_young_moving_repos` — repos that at some day `d` had age ≤ `max_age_days` (by `birth_at`) and
   ≥ `min_stars_14d` stars in `[d-14, d)`. Grain `repo_id`, plus `first_moving_day`. This is the
   superset of all candidates; every expensive model below is restricted to these repos (or, for actor
   models, to their stargazers). This "candidate-first" restriction is what keeps history builds feasible.
4. `int_repo_daily_activity` — grain `(repo_id, day)` for young-moving repos: `n_stars, n_forks,
   n_issues_opened, n_issues_closed, n_issue_events, n_issue_comments, n_pr_comments, n_prs_opened,
   n_prs_closed, n_prs_merged, n_reviews, n_releases, n_creates_branch, n_creates_tag, n_pushes,
   n_pushers, n_distinct_actors` (non-bot, across all types), `detail_level_min`. Use one
   `UNION ALL` of slim per-type projections then `GROUP BY` — not nine joins.
5. `int_actor_daily_activity` — grain `(actor_id, day)` for actors who starred any young-moving repo:
   `n_events` (all kept types incl. pushes), `n_repos` (distinct repos), `n_stars_given`.
   Then `int_actor_cumulative_activity` with running sums per actor ordered by day
   (`SUM(...) OVER (PARTITION BY actor_id ORDER BY day ROWS UNBOUNDED PRECEDING)`).
6. `int_star_events_enriched` — grain: one row per first star on a young-moving repo. Columns:
   `repo_id, actor_id, starred_at, star_day, est_account_created_at` (ASOF JOIN on the actor-age map),
   `account_age_days_at_star`, `actor_events_prior_90d`, `actor_repos_prior_90d`,
   `actor_stars_prior_90d`, `actor_stars_same_day` (stars given on that UTC day across all repos).
   Compute the prior-90d windows as **cumulative(day-1) − cumulative(day-91)** using two
   `ASOF JOIN`s against `int_actor_cumulative_activity` (efficient; avoid a range join over raw events).
   Activity strictly before `star_day` only.
7. `int_contributor_first_seen` — grain `(repo_id, actor_id)`: first contribution time on the repo
   (issue opened, issue/PR comment, PR opened, review, push day), and contribution type.
8. `int_contributor_sessions` — sessionization of **non-push** human activity (issues, comments, PRs,
   reviews) on young-moving repos: order events by `(repo_id, actor_id, created_at)`, `LAG(created_at)`,
   new session when gap > `session_gap_minutes` or first event; `session_id` via running `SUM`.
   Output grain `(repo_id, actor_id, session_id)`: `session_start, session_end, n_events,
   event_types (list)`. Add tests: `session_end >= session_start`, `n_events >= 1`.
9. `int_core_actors_daily` — grain `(repo_id, actor_id, day)` evidence that an actor acts as a
   maintainer: pushed that day, or closed/merged a PR (detail), or the repo owner login equals the actor
   login (owner = first segment of the repo name valid on that day). Phase 7 uses a trailing window of this.
10. `int_issue_response` (detail rows only) — for each `IssuesEvent opened` on young-moving repos:
    `repo_id, number, opened_at, author_id, first_response_at` (first IssueCommentEvent on the same
    `(repo_id, number)` by an actor ≠ author and not a bot, after opened_at), `closed_at`.
    `int_pr_lifecycle` similarly: `opened_at, author_id, closed_at, merged_at (if pr_merged known),
    first_review_at`. Keep timestamps; Phase 7 applies "before D" logic.
11. `int_star_cohort_retention` — for each young-moving repo and weekly star cohort (`date_trunc('week',
    starred_at)`): `n_stargazers`, and the share of those stargazers who later forked / opened an issue
    / opened a PR / commented on the same repo within 30, 60 and 90 days after their star. Showcase model
    for the site's retention heatmap (Phase 11). Also expose the event-level link table
    `int_stargazer_later_actions` for point-in-time features in Phase 7.

## Tests (beyond not_null/unique on every grain)
- `accepted_values` on `event_type`, `ref_type`, `review_state`, `action` (values from the schema audit).
- Custom generic tests in `dbt/tests/generic/`:
  - `no_rows_outside_window(column)` — staging respects `events_start/events_end`.
  - `monotonic_cumulative` on `int_actor_cumulative_activity`.
  - `birth_not_after_first_star` (allow small tolerance; report count rather than fail if < 0.1%).
- Singular tests: `stg_stars` has no duplicate (repo_id, actor_id); `int_repo_daily_activity.n_stars`
  sums equal `int_repo_star_daily` for young-moving repos.
- Row-count sanity (`dbt_utils.expression_is_true` or a custom test) with `severity: warn`.

## CLI
- `breakout build dbt -- run --select staging+ --vars '{events_start: 2025-04-01}'`
- `breakout build history` → full-history build of staging + intermediate (`--vars` covering all history).
  Log wall time per model (`dbt run` already prints it) and the DuckDB file size.
- If a model runs out of memory or exceeds ~2 hours, fall back to batching by year: add var
  `batch_year`, materialize that model `external` partitioned by year, and loop years in the CLI.
  Record what you did in an ADR.

## Acceptance criteria
- [ ] `breakout build dbt -- build --select staging intermediate` passes all tests on the fast-start slice.
- [ ] `breakout build history` completes on the available history; row counts and runtimes per model in PROGRESS.
- [ ] `dbt docs generate` works (published in Phase 13).
- [ ] Spot-check query in your report: for 3 well-known repos that broke out in the slice (pick from
      trending data), print their first 30 days of `int_repo_daily_activity`.
- [ ] No model joins on `repo_name` (grep check in a unit test: fail if `join` lines reference `repo_name`).
