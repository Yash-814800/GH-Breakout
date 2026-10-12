# Phase 10 — The website (Astro static site on GitHub Pages)

## Goal
A fast, honest, good-looking public site, rebuilt and deployed by the daily workflow:
leaderboard, repo detail pages, live track record, backtest "time machine", in-browser SQL explorer,
methodology, pipeline status. Zero servers, zero cost.

## Prerequisites
Phase 09 done (daily run produces predictions, outcomes, status). GitHub Pages source = GitHub Actions.

## Architecture
- `site/` is an Astro project with `output: 'static'`. Data is generated **before** the build into
  `site/public/data/` by `breakout publish site-data` and read at build time (pages) or at runtime (charts,
  explorer). `site/public/data/` is git-ignored.
- GitHub Pages project sites live under `/<repo-name>/`. In `astro.config.mjs` set
  `site: 'https://<user>.github.io'` and `base: '/<repo-name>'` from env (`SITE_URL`, `BASE_PATH`) so
  alternative hosts can use `/`. **Every internal link and fetch must use `import.meta.env.BASE_URL`.**
  Add a build-time check that fails if any generated HTML contains `href="/` or `src="/` without the base.
- Charts: Observable Plot (`@observablehq/plot`) rendered client-side from small JSON files.
- Explorer: `@duckdb/duckdb-wasm` bundled via Vite, querying Parquet files served **from the site itself**
  (same origin). Do not read Hugging Face URLs from the browser (cross-origin range requests are unreliable there).
- No tracking scripts, no cookies.

## Deliverables

### 10.1 `breakout publish site-data` (extend the Phase 9 stub) → `site/public/data/`
- `leaderboard.json` — today's top `site.leaderboard_size`: `rank, repo_id, repo_name, html_url, description
  (display only), language, age_days, stars_total_observed, stars_7d, spark_stars_28d (array of 28 ints),
  prob, prob_label` ("~1 in 4"), `explanation, first_flagged_date, days_on_board, rank_change (new/up/down/same),
  suspicion_score` (null until Phase 11), `b1_rank`.
- `repos/<repo_id>.json` for every repo flagged (top `leaderboard_size`) in the last `site.detail_pages_days`:
  metadata, daily stars since birth (from window + history if available), prediction history (date, rank, prob),
  latest SHAP top contributions (feature, value, contribution, sentence), realized outcome if matured,
  trending appearances, HN stories (if enabled). Keyed by **repo_id** (names change).
- `track_record.json` — for each matured live snapshot date: top-25 list with realized `gain_30d`, label, hit flag;
  per-date precision@10/25/50 for model and B1; cumulative calibration bins (predicted vs realized, counts);
  ledger summary (first date, number of rows, last row hash).
- `backtest.json` + `data/explorer/oof_top100.parquet` — from Phase 8 OOF predictions: top 100 per historical
  snapshot with outcomes (clearly labeled "simulated, out-of-fold"). Enforce `site.explorer_max_mb` total for
  explorer Parquet (downsample older years if needed).
- `data/explorer/live_predictions.parquet` — all live predictions (top 200/day) joined with outcomes where matured.
- `status.json` — from run status + drift + registry: last run time, step durations, rows ingested per type for the
  last 14 days, missing hours, dbt freshness/test summary, model version and holdout metrics, drift flags.
- `meta.json` — build time, model version, data through date, counts.
- Validate every JSON against a small JSON Schema in `site/schemas/` (python `jsonschema` in the publish step).

### 10.2 Pages (Astro, `site/src/pages/`)
1. `/` **Leaderboard**: table (rank, repo, language, age, stars 7d + sparkline, probability, why flagged,
   days on board, change). Client-side filters: language, minimum probability, hide suspicious (Phase 11).
   A one-line honest caption: what the probability means, link to methodology and track record. "Data through
   <date>" stamp. Mobile layout as stacked cards.
2. `/repo/[id]/` **Repo detail** (static paths from `repos/*.json`): header with links to GitHub, star history chart
   with prediction markers, "why flagged" with a SHAP bar chart, prediction history, outcome if matured,
   trending/HN appearances, sections reserved for Phase 11 (cohort retention, similar repos, suspicion breakdown)
   rendered only when data exists.
3. `/track-record/` **Live track record**: headline stats (live days, hit rate of top-25 vs base rate vs B1,
   median lead time vs Trending), rolling precision@25 chart (model vs B1), reliability diagram from live data,
   table of matured dates expandable to their top-25 with ✓/✗, explanation of immutability (snapshot repo link,
   ledger CSV link, how to verify the hash chain with `breakout ops verify-ledger`).
4. `/backtest/` **Time machine**: pick a historical date → its simulated top-25 with outcomes. Banner stating
   it is out-of-fold backtest data, not live predictions.
5. `/explore/` **SQL explorer**: DuckDB-WASM loads lazily on this page only; preloaded views over
   `live_predictions.parquet` and `oof_top100.parquet`; 5 example queries (buttons); results table with a
   row cap; errors shown inline. Register files via their same-origin URL (respecting base path). Verify that the
   host serves HTTP range requests (`curl -I -H "Range: bytes=0-100"` on the deployed file); if not, fetch whole
   files with `registerFileBuffer` (files are small by design).
6. `/methodology/`: renders `docs/model_card.md` (copied at build) plus `reports/figures/*` (calibration, PR
   curves, SHAP importance), label definition, candidate definition, evaluation design, limitations.
7. `/status/`: pipeline observability from `status.json` (freshness badge, step timings, rows ingested chart,
   missing hours, drift table, dbt tests summary).
8. `/about/`: what this is, data sources and credits (GH Archive, GitHub, Hugging Face, Wayback-derived trending
   dataset, HN Algolia), contact/issue link, "not affiliated with GitHub", and an opt-out note (repo owners can
   open an issue to be hidden; implement as `config/hidden_repos.yaml` honored by `publish site-data`).

### 10.3 Design
- Decide a distinctive visual direction before coding (not a default template): typography pairing, a restrained
  palette with one accent, clear numeric alignment (tabular numbers), dark mode via `prefers-color-scheme`.
  If a frontend-design skill is available in your environment, use it.
- Accessibility: semantic tables, keyboard-navigable filters, sufficient contrast, charts have text summaries.
- Performance: leaderboard page < 200 KB transferred excluding fonts; no JS framework runtime required for static
  pages (Astro islands only where interactive).

### 10.4 Deploy
- `daily.yml`: the pipeline job uploads `site/public/data` as an artifact **and** uploads it to the derived HF repo
  under `site_data/latest/` (so site-only rebuilds can fetch it). New job `deploy` (`needs: pipeline`, permissions
  `pages: write, id-token: write`, `environment: github-pages`): checkout, download artifact into
  `site/public/data`, `actions/setup-node` (LTS, npm cache), `npm ci`, `npm run build`, base-path check,
  `actions/upload-pages-artifact` (path `site/dist`), `actions/deploy-pages`.
- `site.yml`: on push to `main` touching `site/**` or `docs/model_card.md`: pull `site_data/latest/` from HF,
  build, deploy (same steps).
- Document alternatives in `docs/runbook.md` (do not implement unless the human asks): Vercel Hobby
  (`vercel deploy --prebuilt --prod` with `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, `BASE_PATH=/`),
  Cloudflare Pages (`wrangler pages deploy site/dist` with a Cloudflare API token, free plan).

### 10.5 Tests
- `npm run build` in CI (add to `ci.yml` as a separate job using fixture data in `site/test-data/`, copied into
  `public/data` for the build).
- A Playwright smoke test (optional but recommended): leaderboard renders ≥ 1 row, a repo page renders, explorer
  runs `SELECT count(*)` successfully.
- Python tests for `publish site-data` (schemas validate, hidden repos excluded, size limits enforced).

## Acceptance criteria
- [ ] Site live at `https://<user>.github.io/<repo>/`, all pages load without console errors, links respect base path.
- [ ] Explorer runs the example queries in the deployed site (state whether range requests worked).
- [ ] Daily workflow redeploys automatically with fresh data; `meta.json` shows today's date after the run.
- [ ] Lighthouse (or similar) run on the leaderboard: performance and accessibility ≥ 90 (report the numbers).
- [ ] Screenshots of each page saved to `reports/site_screenshots/` (small PNGs) and referenced in PROGRESS.
