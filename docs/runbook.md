# Runbook

Operational procedures. Keep each section short and actionable.

## Credential rotation

| Secret | Where | Kind | Expiry | Rotate by |
|---|---|---|---|---|
| `GH_ENRICH_TOKEN` | local `.env` and GitHub Actions secret | classic PAT, **no scopes** (public data only) | 1 year from creation | see below |
| `HF_TOKEN` | local `.env` and GitHub Actions secret | Hugging Face write token | none (revoke manually) | rotate yearly |

**GitHub PAT rotation reminder.** The `GH_ENRICH_TOKEN` classic PAT was created on 2026-10-12 with a
1-year expiry, so it stops working on **2027-10-12**. Put a calendar reminder for 2027-09-28
(two weeks before). To rotate:

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate
   new token. Tick **no scopes**; expiry 1 year; note `gh-breakout enrich YYYY-MM`.
2. Update `.env` locally (`GH_ENRICH_TOKEN=`) and the repository secret
   (Settings → Secrets and variables → Actions → `GH_ENRICH_TOKEN`).
3. Verify: `uv run breakout info` reports `GH_ENRICH_TOKEN: set`, then run any enrich command.
4. Delete the old token. If a token was ever pasted into a chat or log, rotate it immediately.

The daily workflow uses this PAT, not the automatic `GITHUB_TOKEN` (1,000 requests/hour is too low
for the enrichment budget).

> Note (2026-10-12): GitHub restricted the stargazers listing endpoints to repository admins and
> collaborators in July 2026 (changelog 2026-06-30). With a no-scope PAT, `/repos/{o}/{r}/stargazers`
> returns 404 and GraphQL `stargazers` returns an empty list for repositories we do not own.
> `stargazerCount`, search, repo metadata and `/users/{u}/starred` still work. See ADR-010.

## Lake on Hugging Face (Phase 3)

Repos (all public, created by `breakout lake init`; names from `config/project.yaml`):
`gh-breakout-events` (events, push_daily, manifests, `catalog.parquet`, README),
`gh-breakout-derived`, `gh-breakout-snapshots` (**never delete, squash or rewrite**),
`gh-breakout-models` (model repo). `HF_USER` must be set in `.env` and as the Actions variable
`HF_USER`; `HF_TOKEN` is an Actions secret.

**Where bytes go.** `data/` is a symlink to the Lexar SSD, and the Hugging Face cache
(`HF_HOME`) defaults to `data/hf_home` on the same disk, so nothing large lands on `/home`. All
lake commands refuse to run if the lake root is missing (SSD unmounted).

| Task | Command |
|---|---|
| Create repos / refresh cards | `uv run breakout lake init` |
| See what would be uploaded | `uv run breakout lake push --dry` |
| Upload history (resumable) | `systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 uv run breakout lake push --table all` (run in the background, log to a file) |
| Upload a slice | `... lake push --since 2023-01 --until 2023-05` |
| Selective download | `uv run breakout lake pull --types WatchEvent --since 2024-01-01 --until 2024-03-31 [--push-daily] [--to DIR] [--manifests]` |
| Compact a finished month | `uv run breakout lake compact --month 2024-06` (one atomic commit: month files + catalog, day files deleted) |
| Local catalog totals | `uv run breakout lake catalog` |
| Verify | `uv run breakout lake verify [--deep] [--remote]` |
| Backfill one hourly month (Actions job body) | `uv run breakout lake backfill-month 2024-06 --workers 3` |

**Resumability.** A push skips files whose sha256 already matches the remote catalog; every commit
carries the updated `catalog.parquet` and is guarded by `parent_commit`, so an interrupted or
raced upload simply continues. At most `huggingface.max_files_per_commit` files and
`max_bytes_per_commit` bytes go into one commit. A month with `month-` files on the Hub is skipped
by `backfill-month`. Delete nothing locally until `lake verify --remote` is clean.

**Hourly-era backfill.** Run the `hourly-backfill` workflow (Actions -> Run workflow). It plans one
matrix job per month from `history.cutover_date`, ingests, compacts, pushes and writes a manifest
fragment `manifests/hourly/hourly-YYYYMM.parquet` (merged locally by `lake pull --manifests`). It
can be re-run safely; finished months are skipped.

**Squash policy.** The events repo accumulates 1-2 commits a day. After human approval a yearly
`HfApi.super_squash_history` on the **events** repo is allowed (the catalog and git ledger remain
the audit trail). Never squash `gh-breakout-snapshots`; `hf.PROTECTED_REPOS` blocks deletes there.

**If Hugging Face throttles or refuses.** Keep `bq` history in the repo and publish the hourly era
as month files only (ADR-014 item 5); tell the human before deleting anything remotely.

## Feature marts (Phase 7)

Models: `int_actor_early_stars`, `int_actor_early_cum`, `int_repo_first_hit`, `int_tastemaker_thresholds`
(tastemaker inputs), `feat_{star_dynamics,activity,stargazers,tastemaker,owner,detail,enrich}` and
`mart_repo_features` (dbt `models/features/`). All of them read only rows strictly before the snapshot
date; `_max_input_ts` of each group is checked by `dbt/tests/features_no_future_inputs.sql`.

| Task | Command |
|---|---|
| History build + tests + export (resumable per bucket) | `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=100% uv run breakout build features --history` (background; same env as Phase 5: local `GHB_WAREHOUSE`, `GHB_DUCKDB_*`) |
| Rebuild after a feature SQL change | add `--full-refresh` (drops the feature tables; the schema-change check is `fail`) |
| Export only | `uv run breakout build features --history --no-build` |
| Upload the training table | `... --history --no-build --upload` (needs approval: derived repo, `training/`) |
| Live features of one date | `uv run breakout build features --date YYYY-MM-DD [--window-start --window-end]` (warehouse must hold the daily window's staging / intermediate tables) |
| Leak test | `uv run breakout build leak-test --date 2018-05-14 --date 2024-06-03 --sample 300 [--warehouse W]` |
| EDA report | `uv run breakout build feature-eda` |

**Do not edit `dbt/` while a bucketed build is running** (the next bucket's `dbt` call compiles the whole
project and a half-written model aborts the job). For long jobs run from a frozen copy: `cp -r dbt
~/.cache/ghb-dbt-snapshot` and set `GHB_DBT_DIR`, `DBT_TARGET_PATH`, `DBT_LOG_PATH` to it.

**Adding a feature.** Add the column to a `feat_*` model, register it in `config/feature_dictionary.yaml`
(`tests/test_features_dict.py` and the dictionary<->mart check fail otherwise), run
`tests/features` (hand-computed synthetic expectations plus the leak machinery), then rebuild.

## Operations and Daily Pipeline (Phase 9)

Orchestrator and scheduled pipelines running on GitHub Actions (`.github/workflows/`):
- `daily.yml`: daily ingest, feature build, scoring, freeze, ledger append, outcomes, site data, heartbeat.
- `weekly.yml`: retrain, append matured live training rows, champion promotion, PSI feature drift report.
- `monthly.yml`: remote lake verification against the catalog plus a storage summary. The actor-age top-up and the repo metadata refresh are **manual** (they sample the local lake or need live candidate ids; never upload partial enrich tables from a clean runner).
- `health.yml`: keepalive, heartbeat monitoring, automated issue creation.
- `backfill-day.yml`: manual repair for day ranges.

| Task | Command |
|---|---|
| Run daily pipeline locally | `uv run breakout daily run [--date YYYY-MM-DD] [--no-commit] [--no-upload]` |
| Dry run daily pipeline | `make daily DATE=YYYY-MM-DD` |
| Verify ledger integrity | `uv run breakout ops verify-ledger [--remote]` |
| Parity test | `uv run breakout ops parity --date YYYY-MM-DD` |
| Feature drift report (PSI) | `uv run breakout ops drift [--upload]` |
| Append matured live training rows | `uv run breakout ml append-live-training [--upload]` |
| Initialize persistent state | `uv run breakout build state --as-of YYYY-MM-DD [--upload]` |
| Export site data | `uv run breakout publish site-data [--date YYYY-MM-DD]` |

### How to rerun a day
- **In GitHub Actions**: Go to Actions -> `Daily Pipeline` -> `Run workflow`. Enter the snapshot date `YYYY-MM-DD`.
- **Locally**: `uv run breakout daily run --date YYYY-MM-DD`. Rerunning the same day is idempotent: if predictions are already frozen with the same hash, freeze and ledger append are clean no-ops.

### How to repair gaps
- **In GitHub Actions**: Run the `Backfill Days` (`backfill-day.yml`) workflow with `start` and `end` dates (inclusive).
- **Locally**:
  ```bash
  uv run breakout ingest range <start> <end> --force
  uv run breakout lake push --table all --include-days
  ```
  The hourly manifest tracks missing or pending hours; the next daily run automatically plans up to 10 days needing work.

### How to roll back a model
1. Inspect available versions in `data/models/registry.json`.
2. To point champion back to a previous version `<prev_version>`:
   ```bash
   uv run breakout ml promote --candidate <prev_version> --no-if-better
   ```
   Or edit `registry.json` and set `"champion": "<prev_version>"`.
3. Commit and push: `git add registry.json && git commit -m "chore(ml): rollback champion to <prev_version>" && git push`.

### Health alerts and failure modes
The `Pipeline Health & Keepalive` workflow runs every 6 hours and monitors `status/heartbeat.json`:
- **Heartbeat is stale (> 30 hours)**: The daily scheduled cron was skipped, delayed, or failed before recording a successful heartbeat. Check the latest run under Actions -> `Daily Pipeline`. Inspect step durations in `data/run/status.json`.
- **Freeze conflict detected**: Predictions for date `D` were already frozen in the Hugging Face snapshots repository with a different content hash. Predictions are strictly immutable and never overwritten. Investigate whether model weights, dependencies, or input features changed.
- **Missing hours older than 3 days**: GH Archive hours failed to download or parse repeatedly across multiple retry days. Run `backfill-day.yml` or check upstream GH Archive availability.
- **dbt source freshness failed**: Upstream lake tables have not been updated within the expected freshness threshold. Check lake sync logs.

## Website & deployment (Phase 10)

The public static website lives in `site/` (built with Astro) and deploys automatically to GitHub Pages.

### GitHub Pages (default, primary)
- **Deployment**: Automatic via `.github/workflows/daily.yml` after each daily pipeline run, and on code push via `.github/workflows/site.yml`.
- **URL**: `https://<user>.github.io/<repo>/` (configured with `site: 'https://yash-814800.github.io'` and `base: '/GH-Breakout'`).
- **Data flow**: The daily pipeline exports site JSON and Parquet to `site/public/data/` and uploads a copy to Hugging Face derived repo under `site_data/latest/`. Site-only rebuilds pull `site_data/latest/` to stay fresh without rerunning the heavy ML pipeline.
- **Manual local build**:
  ```bash
  uv run breakout publish site-data
  mkdir -p site/public/figures && cp reports/figures/*.png site/public/figures/
  cd site && npm ci && npm run build
  ```

### Alternative static host: Vercel (Hobby tier, $0)
If deploying to Vercel:
1. Set root directory to `site`.
2. Environment variables: `BASE_PATH=/`, `SITE_URL=https://<your-project>.vercel.app`.
3. Build command: `npm run build`, Output directory: `dist`.
4. Deploy with CLI: `vercel deploy --prebuilt --prod` (with `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`).

### Alternative static host: Cloudflare Pages (Free tier, $0)
If deploying to Cloudflare Pages:
1. Build command: `npm run build`, Output directory: `dist`.
2. Environment variables: `BASE_PATH=/`, `SITE_URL=https://<your-project>.pages.dev`.
3. Deploy with Wrangler CLI: `wrangler pages deploy site/dist --project-name gh-breakout` (requires free Cloudflare API token).



## Front-end QA (Phase 14)

Run from `site/`:

| Task | Command |
|---|---|
| Unit tests (formatters, tokens, chart theme) | `npm test` |
| Token lint (no stray colors, palette classes, pixel font sizes) | `npm run lint:tokens` |
| Build on fixture data (adds OG images, checks base paths) | `npm run build:fx` |
| Layout, content, a11y and visual tests | `npx playwright test` (serves `dist-fx`) |
| Internal link check | `npm run check:links` |
| Lighthouse (desktop and mobile) | `npm run lh` (set `CHROME_PATH` to a Chromium) |
| Screenshots of every route, widths and themes | `node scripts/screenshot.mjs --out ../reports/design/after --format jpeg` |
| Contact sheets | `node scripts/contact-sheet.mjs --dir ../reports/design/after` |

- **Visual snapshots** must be made in the pinned image, never on the host (fonts differ):
  `podman run --rm --ipc=host --security-opt label=disable -v "$PWD":/work -w /work/site -e CI=1 mcr.microsoft.com/playwright:v1.64.1-noble npx playwright test tests/visual.spec.ts --update-snapshots`
  (from the repo root, after `npm --prefix site run build:fx`), or run the `update-visual-snapshots` workflow, which opens a PR. Keep the image tag equal to the `@playwright/test` version.
- **Fixtures** (`site/test-data/`) hold the edge cases of the phase file (60-character name, CJK and Arabic descriptions, probabilities 0.004 to 0.97, ...). Regenerate with `npm run fixtures`;
  `node scripts/make-fixtures.mjs --track-days 60 --out /tmp/track_record.json` writes a longer track record for manual checks.
- **Brand name and tagline** live in `config/project.yaml` (`site.brand_name`, `site.tagline`). After a change run `npm run brand` (favicons, manifest) and rebuild; OG images regenerate on their own.
- **Daily deploy gate:** if the content check fails on real data, `daily.yml` skips the deploy and writes a warning to the run summary; fix the data or the formatter and re-run the workflow.


## Distribution (Phase 12)

Everything below is built from frozen prediction snapshots and needs no extra service.

| What | Where | How it is built |
|---|---|---|
| RSS feed of new leaderboard entries | `/feed.xml`, JSON Feed at `/feed.json` | `breakout publish feeds` writes `site/public/data/feed_items.json` (last 100 entries, GUID `repo_id:first_flag_date`); Astro renders both feeds at build time |
| Weekly digest feed | `/digest/feed.xml` | one item per digest |
| Badges | `/badges/<repo_id>.json`, `/badges/by-name/<owner>/<name>.json` | `breakout publish badges` (daily, and in `site.yml`); shields.io endpoint schema; never encodes the unusual-pattern check |
| Weekly digest | `/digest/`, `/digest/<YYYY-Www>/` | `breakout publish digest --week 2026-W43 --upload` in `weekly.yml`; stored on the derived repo under `digests/`; `publish site-data` pulls it |
| Digest in GitHub Discussions | repository Discussions | `breakout publish discuss-digest` in `weekly.yml` (token `GITHUB_TOKEN`, permission `discussions: write`) |

- **Badge paths.** `by-name` files are written in lower case and follow the *current* repo name; after a rename the old path stops updating. Use the `repo_id` path in a README, it is stable.
  The copyable Markdown is on every repo page.
- **Discussions.** GitHub has no API to create a discussion category. Create a category named **Digest** once in the repo settings (Discussions > Categories, announcement format). Until then
  `discuss-digest` posts to **Announcements** and says so in its output. Posts are idempotent: a discussion with the same title (`Weekly digest 2026-W43`) is never created twice.
- **Bluesky bot: not built.** `optional.bluesky_enabled` stays `false` by decision of the owner (ADR-032); there is no Bluesky code in the repository.
- **Mastodon variant (not implemented).** Post the same short text with `POST /api/v1/statuses` and a bearer token of a dedicated bot account. Only do this on an instance whose rules explicitly allow bots,
  mark the account as a bot, post at most a few statuses a day, and keep the same de-duplication rule (a repo at most once in 60 days, never a high-suspicion one).
- **A feed looks wrong.** Check `site/public/data/feed_items.json` first; if it is empty run `breakout publish feeds` (it restores the frozen snapshots from the snapshots repo, read only).
