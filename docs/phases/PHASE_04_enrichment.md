# Phase 04 — Enrichment: repo metadata, actor account age, trending history, Hacker News

## Goal
Add the external data the model and site need, all free:
1. **Repo name history** (name ↔ repo_id over time) — needed to map anything keyed by name.
2. **Repo metadata** from the GitHub API for candidate-like repos (true creation date, fork flag,
   language, owner type, description for display).
3. **Actor-id → account-creation-date map**: GitHub user ids are assigned sequentially, so a small
   sample of `(id, created_at)` pairs lets us estimate any account's age from its id with no further
   API calls. This powers star-quality and fake-star features.
4. **GitHub Trending history** for the "lead time vs Trending" headline metric.
5. **Hacker News stories linking to GitHub repos** (optional feature, `optional.hn_enabled`).

## Prerequisites
- Phase 03 done (lake on HF, `lake pull` works). `GH_ENRICH_TOKEN` set locally.

## Deliverables

### 4.1 Repo name history — `src/breakout/enrich/names.py`
- DuckDB over all `events` files (spine columns only): `SELECT repo_id, repo_name, MIN(created_at)
  first_seen, MAX(created_at) last_seen GROUP BY 1,2`. Write `enrich/repo_name_history.parquet`.
- `resolve_repo_ids(con, names_with_dates) -> table`: for each `(owner/name, as_of)` return the repo_id
  whose name interval contains `as_of`, else the repo_id with that name seen most recently before
  `as_of`, else NULL. Case-insensitive match on name. Unit-test with a renamed-repo example.
- `latest_names` view: most recent name per repo_id (for display and API lookups).

### 4.2 Repo metadata — `src/breakout/enrich/github_meta.py`
- Target set (superset of future candidates, computed now with DuckDB on WatchEvent): repos that got
  ≥ `candidates.min_stars_14d` stars within any 14-day window starting within 120 days of their first
  observed event. Also accept an explicit list of repo_ids (used daily in Phase 9).
- Fetch via **GraphQL** in batches of 50–100 aliased `repository(owner:, name:)` lookups using the
  latest known name. Fields: `databaseId, nameWithOwner, createdAt, isFork, parent { databaseId },
  isArchived, isMirror, isTemplate, primaryLanguage { name }, licenseInfo { spdxId },
  owner { __typename login ... on User { databaseId createdAt } ... on Organization { databaseId createdAt } },
  description, homepageUrl, repositoryTopics(first: 10) { nodes { topic { name } } }, stargazerCount`.
- **Verify `databaseId == repo_id`.** On mismatch or not-found, fall back to REST
  `GET https://api.github.com/repositories/{repo_id}` (works by numeric id, follows renames).
  REST 404 → record `status='not_found'` (deleted or private now). **Keep these rows** — dropping them
  would introduce survivorship bias.
- Rate limiting: read `rateLimit { remaining resetAt cost }` in every GraphQL response and REST
  `x-ratelimit-*` headers; sleep until reset when remaining < 100. Respect secondary rate limits
  (`retry-after`). Max ~1 request/second. Resumable: skip repo_ids already fetched within
  `--max-age-days` (default 30).
- Output `enrich/repo_metadata.parquet` with `fetched_at`, `status`, and all fields. In
  `config/feature_dictionary.yaml` mark which columns are **allowed as model features**:
  `created_at` (fixed), `is_fork` (fixed), `primary_language` and `owner_type` (slowly varying —
  documented exception, add ADR). **Never** features: `stargazerCount`, description, topics,
  homepage, archived (display only).
- CLI: `breakout enrich repos [--repo-ids-file f] [--limit N] [--max-age-days 30]`.

### 4.3 Actor-id → account-age map — `src/breakout/enrich/actor_age.py`
- Get the observed actor_id range from the lake. Choose ~3,000 sample ids: dense quantile spacing over
  the observed distinct actor_ids (sample from real actor_ids, not arbitrary integers, so they exist).
- Fetch `GET https://api.github.com/user/{id}` → `created_at` (404s happen; skip them). Rate-limit as above.
- Build a monotone mapping: sort by id, apply isotonic regression (sklearn `IsotonicRegression`, add
  scikit-learn now) of created_at (as epoch seconds) on id; store breakpoints as
  `enrich/actor_id_age_map.parquet (actor_id_breakpoint BIGINT, est_created_at TIMESTAMP)`.
- Provide a DuckDB macro/SQL snippet (also used in dbt) using `ASOF JOIN` on `actor_id >= breakpoint`
  to get `est_account_created_at` for any actor.
- Validate on a 10% hold-out: report median absolute error in days, and error by id decile, in
  `docs/PROGRESS.md`. Expect days-to-weeks accuracy; if median error > 60 days, investigate.
- The map must be refreshed monthly (new ids keep appearing): ids above the max breakpoint get the max
  date (+ flag `est_is_extrapolated`). Phase 9 schedules a monthly top-up of ~200 new samples.
- CLI: `breakout enrich actor-age [--samples 3000]`.

### 4.4 Trending history — `src/breakout/enrich/trending.py`
- Historical source A: the Hugging Face dataset `ronantakizawa/github-top-projects` (daily trending
  entries scraped from Wayback Machine snapshots, 2013–2025). Load with DuckDB from `hf://` or
  `huggingface_hub`; **inspect its actual columns first**; check its license and record it in an ADR.
- Historical source B (fill the gap after source A ends): search GitHub for an actively updated daily
  trending archive repo (for example `antonkomarev/github-trending-archive`); read its files from its
  git history/raw files. Verify date coverage. Use whichever sources are reliable; union them.
- Going forward (Phase 9 runs it daily): fetch `https://github.com/trending?since=daily` once per day.
  **First check `https://github.com/robots.txt`**; if `/trending` is disallowed for generic agents, do
  not scrape — rely on source B instead and record the decision in an ADR.
- Normalize to `enrich/trending.parquet (date, rank, repo_name, language_filter, source, repo_id)`;
  resolve `repo_id` with `resolve_repo_ids(name, date)`.
- Write a coverage table (days with ≥ 1 entry per month) into `docs/PROGRESS.md`. The lead-time metric
  (Phase 8) is only computed on covered dates.
- CLI: `breakout enrich trending-history`, `breakout enrich trending-today`.

### 4.5 Hacker News (optional) — `src/breakout/enrich/hn.py`
- Use the free Algolia HN API (no key):
  `https://hn.algolia.com/api/v1/search_by_date?tags=story&query=github.com&restrictSearchableAttributes=url&numericFilters=created_at_i>{a},created_at_i<{b}&hitsPerPage=1000`.
  Slice time windows adaptively (start with 7 days; if `nbHits >= 1000`, halve the window) so every slice
  returns < 1000 hits. Throttle to ≤ 1 request/second; resumable by window.
- Parse `url` → `owner/name` only for `github.com/<owner>/<repo>[/...]` URLs (strip `.git`, query strings,
  fragments; ignore `github.com/<owner>` alone, `gist.github.com`, `github.com/orgs/...`, `/topics`,
  `/sponsors`, `/marketplace`, etc.). Resolve to repo_id as of the story time.
- Output `enrich/hn_stories.parquet (story_id, created_at, points, num_comments, title, url, repo_name, repo_id, fetched_at)`.
- Leakage note (record in feature dictionary): `points` and `num_comments` are final values at fetch time.
  Features may use story **counts** with `created_at < D`, and points only for stories created before
  `D - 3 days` (by then most points have accrued). Document this approximation.
- CLI: `breakout enrich hn-history --since 2015-01-01`, `breakout enrich hn-recent --days 3`.

### 4.6 Shared
- All outputs written locally under `data/derived/enrich/` and uploaded to the **derived** HF repo under
  `enrich/` via `lake.hf.upload_files`.
- `src/breakout/enrich/http.py`: one shared `httpx.Client` factory with user agent
  `gh-breakout (+https://github.com/<user>/gh-breakout)`, timeouts, retry policy, and rate-limit helpers.
- Tests: URL parsing (table-driven, ≥ 20 cases), name resolution with renames, isotonic map monotonicity
  and ASOF lookup, GraphQL response parsing from saved JSON fixtures (no live calls in tests), rate-limit
  sleep logic with a fake clock.

## Rules / gotchas
- Never send the token anywhere but api.github.com. Never log it.
- Never use current `stargazerCount` for labels or features.
- API-derived `created_at` is the true repo creation time; repos made public later have a `PublicEvent`
  — Phase 6 defines "birth" using both.

## Acceptance criteria
- [ ] `enrich/repo_name_history.parquet`, `repo_metadata.parquet`, `actor_id_age_map.parquet`,
      `trending.parquet` (and `hn_stories.parquet` if enabled) exist locally and on HF.
- [ ] Report: metadata coverage (% found / not_found), actor-age hold-out error, trending coverage by month,
      HN story count by year and % resolved to repo_id.
- [ ] Re-running each command is incremental (does not refetch fresh rows).
- [ ] ADRs for: allowed metadata features, trending sources + robots.txt decision, HN points approximation.
