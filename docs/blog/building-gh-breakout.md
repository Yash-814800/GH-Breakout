---
title: Building Breakout Radar for $0
date: 2026-10-21
description: How a free, public leaderboard of GitHub repos that are about to break out was built without a server, a database or a credit card, and what went wrong on the way.
---

Every day thousands of new GitHub repositories get their first stars. A handful, about one in two hundred of the ones that already have momentum, go on to gain stars at a pace most never reach. **Breakout Radar** tries to name those repos before it happens, publishes the list every morning, and keeps a record that nobody, including me, can quietly edit afterwards.

This post is the story of how it was built: the problem, the label, the architecture and its constraints, the defences against leakage, the results, and the things that did not work. All numbers are from the repository; the files they come from are named.

## The problem, and why "will gain 1,000 stars" is the wrong target

The first idea is a fixed target: "will this repo gain 1,000 stars in the next 30 days?". It looks clear and it is a bad label.

- **The base rate moves.** GitHub grows, star behaviour changes, and the star stream that the public archive captures changed twice during this project (see below). A fixed threshold turns a model into a measure of how much attention GitHub got that year.
- **Candidates differ in size.** A repo with 5,000 stars needs a different push to reach +1,000 than a week-old repo with 20.

So the label is relative. A *breakout* is a candidate whose 30-day star gain in `[D, D + 30)` is at least `max(100, the 0.995 quantile of the gain of all candidates on the same snapshot D)`. By construction about 0.5% of rows are positive in every year (0.51% pooled), and the question stays comparable over time. The definition of a *candidate* is a single SQL model used for training and for the daily run: age at most 90 days, fewer than 200 stars before D, at least 5 stars in the 14 days before D, and no forks, mirrors or bot-owned repos.

Time is handled with one rule: a snapshot `D` is the world as known at `D 00:00 UTC`. Features may use only events before `D`. A label is *matured*, and may be used, only when its 30 days have elapsed and been ingested.

## A free architecture and the constraints that shaped it

The project has a hard rule: it runs for $0 with no credit card anywhere. That ruled out most of the usual data stack and shaped everything:

| Need | Choice | Constraint that decided it |
|---|---|---|
| 10 years of history | Google BigQuery **sandbox** (no billing account) | 1 TB of queries a month. The JSON `payload` column is most of the bytes, so the history was extracted as *spine* columns only: 522.7 GB billed for 101 months, 3.26 billion events |
| Daily and recent data | GH Archive hourly files, parsed in GitHub Actions | The ~2 TB hourly backfill ran as a GitHub Actions matrix, not on the laptop (an earlier heavy local job had crashed the developer's session) |
| Storage | Hugging Face public dataset repos | Free for public data; commits capped at 1.5 GB because the client ran out of memory above that. 116 GB today |
| Compute | DuckDB, dbt-duckdb | No server, runs on the laptop and in CI |
| Site | Astro on GitHub Pages | Free, and the site is just static files |
| SQL in the browser | DuckDB-WASM over Parquet served from the site itself | Hugging Face's CDN does not reliably allow cross-origin range requests, so the browser cannot read Parquet from it. The files are copied next to the pages |

Three external facts changed the plan along the way, and each is recorded as a decision (ADR) in `docs/DECISIONS.md`:

1. **GitHub trimmed event payloads on 2025-10-07** (commit lists, many pull-request fields, `author_association`). Features were split into tiers: tier A needs only the event spine and works for all history, tier B needs payload details and exists from mid-2023, tier C is enrichment. The live model uses only features that survive the trim.
2. **GH Archive stopped capturing most stars on 2025-05-24.** Compared with the same weekday in 2024, stars per day fell to about 70% on that day, to roughly 45% by late 2025 and to about 1% in mid-2026. The other event types stayed normal. Training and evaluation therefore end on 2025-05-23, and the website takes current star counts from GitHub's API instead of the archive.
3. **GitHub restricted the stargazers listing to admins and collaborators in July 2026.** So no token of ours can list who starred a repo; only counts are available. The daily cross-check uses count deltas.

## Defences against leakage

A model that predicts the future from data that already contains the future looks wonderful and is worthless. The project spends more code on preventing that than on the model:

- **Point-in-time features.** Every feature table is built by the same SQL for history and for the daily run, with `created_at < D` as the only allowed time filter. A dbt test fails if any source row used is on or after `D`.
- **A time-travel leak test.** `breakout build leak-test` copies a sample of 300 candidates and everything their features read into two small databases, one complete and one cut at `D`, rebuilds the features in both with the real dbt models, and requires every one of the 71 columns to be equal. It passes on four dates. A mutation check proves the test can fail: changing `<` to `<=` in one feature model makes it red.
- **Outcome-dependent features use matured labels only.** The "tastemaker" feature (did recent stargazers pick early stars that later took off?) may only count outcomes that were known before `D`.
- **No random splits.** Evaluation is rolling-origin: 29 expanding folds with 3-month test blocks and an embargo of 30 days, the label horizon, between the last training snapshot and the first test snapshot. Metrics are reported per year as well as pooled.
- **Calibration on data the model never trained on.** The last 3 months of the training window train the calibrator, not the booster.
- **Sanity checks that must fail.** A model trained on permuted labels scores PR-AUC 0.0058 against a 0.5% base rate; a model on permuted test labels scores 0.0050. Both behave like chance.
- **Training and serving parity.** The daily pipeline rebuilds the features of a historical Monday and matches the history mart: 100% of candidates, 99.99% of cells.

## Results against the baseline

The baseline is the obvious one: rank by stars gained in the last 7 days. A model is promoted only if it beats the baseline on PR-AUC and precision at 25.

| Out-of-fold, pooled over 29 folds, 2018 to May 2025 | PR-AUC [95% CI] | Precision@25 [95% CI] |
|---|---|---|
| LightGBM, calibrated | 0.108 [0.102, 0.114] | 0.241 [0.228, 0.255] |
| Baseline: 7-day star velocity | 0.029 [0.025, 0.035] | 0.109 [0.100, 0.118] |

The model wins in all 29 folds. On a 26-week holdout the evaluation model scores PR-AUC 0.158 and precision@25 0.338 against 0.032 and 0.106. About 24% of the top 25 of an average snapshot are real breakouts, in a pool where 0.5% are. Against GitHub Trending, among 3,053 repos that reached Trending, the model flagged 22% before they appeared there, with a median lead of 1 day (the velocity baseline: 9% and 0 days). That is a modest lead and the page says so: most Trending repos, 63%, were never in the top 25 at all.

## The track record

A prediction is only worth something if it cannot be changed after the fact. Each day the predictions are written to an immutable snapshot on Hugging Face, and one row goes into `ledger/predictions.csv` in git: the date, the model version, the SHA-256 of the file and of the top-50 ids, and the hash of the previous row. Changing any past row breaks every row after it, and `breakout ops verify-ledger` checks the chain each day.

Honesty about how short this is: the first live list is from 2026-10-20, and a list matures 30 days later, so the first hit rate can only be computed on 2026-11-19. Until then the track-record page says that it has nothing to judge yet and shows the historical back-test, labelled as a simulation.

## What did not work

- **The first baseline was too easy.** A `NULL` in a bot-owner filter silently dropped every repo without stored metadata from the candidates. The numbers looked fine (the baseline's PR-AUC was 0.052), and they were survivorship-biased. It surfaced only when the live run returned zero candidates. After the fix the baseline's PR-AUC is 0.029, the bar for the model is lower and honest, and a test now fails if a candidate table contains no repo with unknown metadata (ADR-024).
- **Detail and enrichment features add nothing measurable.** The tier A features alone reach the same PR-AUC (+0.006, interval including zero). They stay in the model, but the hypothesis that payload details help is not supported by this data.
- **A calibrator trained on Mondays over-predicts on other days.** Scoring 28 daily snapshots showed observed/expected positives of 0.90 on Mondays and about 0.73 on the other days. Ranking quality is unaffected within the noise, the probabilities are a little too high.
- **Hand-written insight texts contradicted their own charts** and one of them used loaded wording about star farming. They are now generated from the chart data, with neutral wording.
- **A faster star source was not an option.** The OpenDigger mirror downloaded at about 0.01 MB/s from a GitHub runner against 54 MB/s for GH Archive, so it never became the live source.
- **Big builds die quietly under memory caps.** A global sort over a month of wide rows ran out of memory; the fix was to deduplicate per day and sort in a separate pass. Everything heavy now runs under a hard memory limit with one worker.

## Try it

The live site is at <https://yash-814800.github.io/GH-Breakout/>. The code, the ledger and the methodology are in the [repository](https://github.com/Yash-814800/GH-Breakout), the data is on [Hugging Face](https://huggingface.co/Yasshh814), and the [data model docs](https://yash-814800.github.io/GH-Breakout/dbt-docs/) show every table the model is built from.
