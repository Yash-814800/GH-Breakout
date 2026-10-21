# Portfolio summary

Numbers are measured and come from `reports/`, `docs/PROGRESS.md` and the live site (2026-10-21). The live track record
is two days old, so no live hit rate is claimed anywhere below.

## Résumé bullets

- **Built an end-to-end forecasting product on a $0 stack:** a daily public leaderboard of young GitHub repositories likely to gain an unusual number of stars in the next 30 days (GitHub Actions, Pages, Hugging Face, DuckDB, dbt, LightGBM, Astro), with 10 scheduled and manual workflows and no card-gated service.
- **Processed 5.6 billion GitHub events (115 GB of Parquet)** from 2015 to today: 3.26 B events extracted from BigQuery's free sandbox (522.7 GB billed against a 1 TB monthly quota) and about 2 TB of hourly GH Archive files downloaded across a 41-job Actions matrix, all under a 4 GB memory cap on a 15 GB laptop.
- **Modelled with leakage defences and honest evaluation:** point-in-time features (71 columns), a time-travel leak test with a mutation check (300 repos, four dates, zero differing values), rolling-origin CV with a 30-day embargo over 29 folds, and calibration on data the booster never saw. The model reaches PR-AUC 0.108 (95% CI 0.102 to 0.114) against 0.029 for a 7-day-velocity baseline, and precision@25 of 0.241 against 0.109; it wins in all 29 folds.
- **Engineered data quality at scale:** 52 dbt models in four layers, every one of 500 columns documented, 274 dbt tests, 390 Python tests, 41 unit and 178 browser tests (layout, accessibility, visual snapshots), training and serving parity of 99.988% of feature cells on a replayed day, and a SHA-256 hash-chained prediction ledger verified daily.
- **Shipped the product and its distribution:** a static Astro site (Lighthouse 99 to 100 performance, light and dark themes, 360 px to 1920 px), DuckDB-WASM SQL in the browser, RSS and JSON feeds, shields.io badges, a weekly digest and a suspicious-growth detector, all rebuilt daily in about 4 to 7 minutes.
- **Measured instead of assuming:** a published DuckDB versus ClickHouse benchmark on the same Parquet files (seven queries, all reported): DuckDB was 1.5 to 3 times faster on five, ClickHouse was faster on distinct counts, and ClickHouse could not finish two queries in 4 GB.

## 60-second pitch

"Every day thousands of GitHub repos get their first stars, and about one in two hundred of the ones with momentum goes on to take off. I built Breakout Radar to name those repos before it happens. It ingests GH Archive, builds point-in-time features with dbt and DuckDB, scores today's candidates with a calibrated LightGBM model and explains each score in a sentence. The result is a free public leaderboard, with a track record that can't be edited, because every day's predictions are frozen and chained with hashes. The whole thing runs on free services: GitHub Actions and Pages, Hugging Face for the data, BigQuery's sandbox for the one-time history. What I care about most is that the evaluation is honest: no random splits, an embargo equal to the label horizon, a baseline the model has to beat in every fold, and a live record that I'm explicit about being only days old."

## Five likely interview questions

**1. How did you prevent leakage?**
By construction and by test. Features for snapshot `D` come from SQL that may only read events before `D`; outcome-dependent features (the "tastemaker" score, an owner's earlier breakouts) may only use labels that matured before `D`. A dbt test fails if any source row on or after `D` is used. The time-travel leak test rebuilds the features for 300 sampled repos from inputs cut at `D` and demands equality in all 71 columns, and a mutation check (`<` changed to `<=`) proves the test can fail. Evaluation never splits randomly: rolling-origin folds with a 30-day embargo equal to the label horizon. Sanity runs with permuted labels score chance level (PR-AUC 0.006 and 0.005 on a 0.5% base rate).

**2. Why isn't the label "gains 1,000 stars"?**
A fixed threshold makes the base rate depend on how much attention GitHub got that year, and on the size of the repo. The label is relative: the 30-day gain is at least the 0.995 quantile of the candidates' gain on the same snapshot, with a floor of 100 stars. About 0.5% of rows are positive in every year, so metrics are comparable across years and the daily list asks the same question every day.

**3. How is calibration handled, and where does it fall short?**
Isotonic regression fitted on the last three months of training dates, which the booster did not train on (calibration error 0.0002 out of fold). It is trained on Monday snapshots, and a check on daily snapshots shows it over-predicts on other weekdays (about 73% of expected positives happened, against 90% on Mondays). The ranking is unaffected, so I documented it on the methodology page and in the model card, and listed retraining on daily snapshots as the fix.

**4. Why DuckDB, and what did you measure?**
The pipeline runs in a daily free GitHub Actions job: DuckDB is a library, so there is nothing to host, and the same SQL runs on the laptop, in CI and (via WASM) in the browser. I measured it against ClickHouse on the same Parquet files: DuckDB was 1.5 to 3 times faster on five of seven queries and used far less memory, ClickHouse was faster on distinct counts, and ClickHouse could not finish the window and join queries within 4 GB. Caveats are in the post: one machine, Parquet rather than ClickHouse's native storage, defaults.

**5. How do you handle fake stars?**
Not by deleting them. A transparent score from six signals on a candidate's recent stargazers (new accounts, no prior activity, bulk starring the same day, one-hour bursts, lockstep co-starring, no later engagement) becomes a neutral "unusual star pattern" label. It is display-only: it never feeds the model and the site never says "fake". I validated it against the published StarScout dataset (81 of 15,773 historical positives, 0.51%, showed high suspicion), checked by ablation that relabeling those changes holdout PR-AUC negligibly (0.1407 against 0.1396), and added a review-request path for maintainers who want to explain a spike.
