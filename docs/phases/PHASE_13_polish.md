# Phase 13 — Portfolio polish, dbt docs, ClickHouse benchmark, final audit

## Goal
Turn a working system into a convincing portfolio piece: clear README with real numbers, published dbt
lineage docs, a fair DuckDB-vs-ClickHouse benchmark write-up, a "how I built it" post, and a final
security / cost / reproducibility audit.

## Prerequisites
Phases 00–12 done (11–12 may be partially done; note what's missing).

## Deliverables

### 13.1 README.md (rewrite)
- One-sentence pitch + link to the live site + hero screenshot (from `reports/site_screenshots/`).
- "Results" box with **real measured numbers** pulled from `reports/` and the live track record: PR-AUC and
  precision@25 vs baseline (with CIs), median lead time vs GitHub Trending, live hit rate so far, days running.
  If live data is still short, say so explicitly.
- Architecture diagram as a Mermaid flowchart (data flow from ARCHITECTURE.md).
- "Runs for $0" table: each service, what it is used for, free limit, current usage.
- Tech highlights: layered dbt models (with link to dbt docs), sessionization and cohort SQL snippets (short),
  point-in-time feature design and leak test, rolling-origin evaluation with embargo, calibration, SHAP sentences,
  immutable track record with hash-chained ledger, suspicious-growth detector.
- Reproduce: prerequisites, `make setup`, how to run phases, how to run locally on a small slice
  (`--since` last 3 months), links to HUMAN_SETUP and runbook.
- Data: link to the HF datasets + dataset cards; license and attribution notes.
- Limitations section (honest).

### 13.2 dbt docs on the site
- In `daily.yml` (or `site.yml`), run `dbt docs generate` against a small fixture warehouse or the window warehouse,
  copy `target/index.html`, `manifest.json`, `catalog.json` into `site/public/dbt-docs/`, and link it from
  `/methodology/` and the README. Ensure every model and important column has a description (add a CI check that
  fails if a model in `models/marts` or `models/intermediate` lacks a description).
- `docs/data_dictionary.md` generated from dbt `manifest.json` (script `breakout publish data-dictionary`).

### 13.3 DuckDB vs ClickHouse benchmark (blog post)
- Use **clickhouse-local** (free single binary; no server) and DuckDB on the same Parquet files: one full year of
  `WatchEvent` + `IssueCommentEvent` + `PullRequestEvent` from the lake. Same laptop, same files, file cache warmed
  identically; report hardware.
- 6 equivalent queries (write both dialects, verify identical results by comparing outputs):
  1. Daily stars per repo for the year (GROUP BY)
  2. Top 100 repos by 7-day star velocity on 12 dates (window functions)
  3. Sessionization of comment activity with a 30-minute gap (LAG + running sum)
  4. Weekly stargazer cohort retention (self-join stars → later actions)
  5. Co-star overlap for 100 repos (self-join on actor)
  6. Exact `COUNT(DISTINCT actor_id)` per month vs approximate (`approx_count_distinct` / `uniq`)
- Method: 1 cold + 5 warm runs each, report median and min, peak memory if measurable. Script it:
  `benchmarks/run.py` (results to `benchmarks/results.json`).
- Write `docs/blog/duckdb-vs-clickhouse.md` and publish at `/blog/duckdb-vs-clickhouse/`: setup, queries, results
  chart, discussion of why the project chose DuckDB (serverless in CI), caveats (single machine, Parquet not native
  MergeTree, versions). No cherry-picking: report every query.

### 13.4 "How I built it" post
`docs/blog/building-gh-breakout.md` → `/blog/building-gh-breakout/`: the problem, label design and why "will gain
1,000 stars" is the wrong target, the free architecture and its constraints (BigQuery sandbox budget, payload
trimming in 2025, CORS), leakage defenses, results vs baseline, the track record, what didn't work.

### 13.5 Final audit (write `reports/final_audit.md`)
- **Security**: gitleaks over full history; every workflow has minimal `permissions`; third-party actions pinned
  to SHAs; no secrets in logs (search recent run logs for token prefixes); Dependabot (or Renovate) config for
  pip, npm, and GitHub Actions; `SECURITY.md`.
- **Cost / limits**: re-verify each free service's current limits from official docs (Actions, Pages, HF storage
  guidance, BigQuery sandbox) and compare with current usage (HF storage per repo, Pages site size, weekly job
  runtime, daily runtime trend). List anything within 50% of a limit.
- **Reproducibility**: fresh clone in a temp dir → `make setup` → run tests → run `breakout daily run --date <recent>
  --no-upload --no-commit` against HF data. Fix whatever breaks; document.
- **Correctness**: rerun the leak test, the daily/history parity test, and ledger verification; attach summaries.
- **Code quality**: coverage report (aim ≥ 70% for `src/breakout`), mypy clean, ruff clean, dead-code scan.
- **Housekeeping**: code license (HUMAN DECISION: MIT or Apache-2.0), `CITATION.cff`, `CONTRIBUTING.md` (short),
  issue templates (bug, review request), repository topics/description suggestions for the human to set.

### 13.6 Portfolio summary for the human
`docs/portfolio_summary.md`: 4–6 résumé bullets with real numbers (data volume processed, models/tests count,
metrics vs baseline, lead time, runtime, $0 cost), a 60-second project pitch, and 5 likely interview questions with
concise answers grounded in this repo (leakage, label design, calibration, scaling choices, fake-star handling).

## Acceptance criteria
- [ ] README renders well on GitHub with real numbers and working links.
- [ ] `/dbt-docs/` live with lineage graph; description CI check passes.
- [ ] Benchmark post live with reproducible script and results JSON.
- [ ] `reports/final_audit.md` complete; all blocking findings fixed or listed for the human.
- [ ] `docs/portfolio_summary.md` written.
