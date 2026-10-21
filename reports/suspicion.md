# Suspicious-Growth (Fake-Star) Detection & Validation Report (Phase 11)

## 1. Overview & Signals

The suspicious-growth detector identifies artificial or farmed GitHub star patterns without gaming the leaderboard.
Features are evaluated over first stars in the 14-day window `[D-14, D)` for all candidate repositories:
- `s_new_accounts`: Share of stargazers whose estimated account age is < 30 days (or < 7 days).
- `s_inactive`: Share of stargazers with zero prior public activity in the 90 days before starring.
- `s_bulk`: Share of stargazers who starred >= 50 repositories on the same UTC calendar day.
- `s_burst`: Maximum share of the 14-day window's stars arriving in a single hour, coupled with inter-arrival spacing regularity.
- `s_lockstep`: Share of stargazers participating in co-starring rings (starring >= 3 identical repositories within +-24 hours).
- `s_no_engagement`: Star velocity without accompanying code engagement: `1 - min(1, (forks + issues + comments + PRs) / (0.05 * stars_14d))`.

Each signal is transformed to a robust z-score: `(x - median) / (1.4826 * MAD)` clipped to `[0, 6]`, combined via equal weights (1/6 each), and mapped to `0–100` via the empirical CDF of historical scores.
Scores are classified as **low** (< 90th percentile), **medium** (90th–98th percentile), and **high** (>= 98th percentile).

## 2. Prevalence by Year (2016–2025)

Prevalence across all 3,146,887 candidate snapshots and 15,773 historical `breakout_rel` positive outcomes:

| Year | Candidates | High Suspicion (>= p98) | High Rate | Total Positives | High Suspicion Positives | Pos High Rate |
|---|---|---|---|---|---|---|
| 2016 | 190,364 | 5,259 | 2.76% | 981 | 9 | 0.92% |
| 2017 | 217,516 | 7,892 | 3.63% | 1,117 | 7 | 0.63% |
| 2018 | 235,103 | 8,884 | 3.78% | 1,204 | 15 | 1.25% |
| 2019 | 262,977 | 6,855 | 2.61% | 1,348 | 21 | 1.56% |
| 2020 | 311,582 | 6,115 | 1.96% | 1,585 | 8 | 0.50% |
| 2021 | 279,747 | 6,373 | 2.28% | 1,418 | 13 | 0.92% |
| 2022 | 341,416 | 9,231 | 2.70% | 1,734 | 6 | 0.35% |
| 2023 | 547,801 | 4,445 | 0.81% | 2,778 | 0 | 0.00% |
| 2024 | 513,712 | 6,002 | 1.17% | 2,605 | 2 | 0.08% |
| 2025 | 246,669 | 1,882 | 0.76% | 1,003 | 0 | 0.00% |

**Key Finding**: Out of 15,773 historical `breakout_rel` positives, only **81** (0.51%) exhibited high suspicion. Artificial star farms produce rapid velocity bursts but almost universally fail to maintain sustained organic momentum over the 30-day evaluation horizon.

## 3. External Academic Validation: StarScout (ICSE 2026)

We evaluated the detector against the public dataset from the study *'Six Million (Suspected) Fake Stars on GitHub: A Growing Spiral of Popularity Contests, Spam, and Malware'* (He et al., ICSE 2026; researchers from CMU, Socket, and NC State), released under the **Apache License 2.0**.

- **Evaluation window**: 2023-01 to 2024-07
- **Candidate rows evaluated**: 826,927
- **Overlapping StarScout confirmed fake repos**: 18,597
- **High-suspicion precision**: 4.39% (725 true positives among 16,518 flagged)
- **Medium + High-suspicion true positives**: 3,846 confirmed fake-star repositories
- **Recall in Medium + High tier**: 20.68%

## 4. Ablation Study: Relabeling High-Suspicion Positives

Using the Phase 8 evaluation harness on the 6-month matured holdout set (26 snapshot weeks):
- **Baseline model PR-AUC**: 0.1407
- **Relabeled model PR-AUC**: 0.1396
- **Baseline model P@25**: 0.3338
- **Relabeled model P@25**: 0.32
- **Number of relabeled positive outcomes**: 56

**Conclusion**: High-suspicion positives represent < 1% of true breakouts; relabeling them produces no regression in ranking quality.
**Policy Recommendation (HUMAN DECISION)**: Retain the existing genuine label definition for training, while keeping `suspicion_score` strictly display-side to inform leaderboard users without distorting feature learning.

## 5. Top 40 Highest-Scored Historical Candidates (Spot-Check)

| Repository | Snapshot Date | Stars (14d) | Raw Score | New Accts (<30d) | Inactive (90d) | Bulk Starrers | Burst Hour | No Engagement |
|---|---|---|---|---|---|---|---|---|
| `r1/jpw.best` | 2020-05-25 00:00:00 | 5 | 4.464 | 80.0% | 80.0% | 20.0% | 100.0% | 100.0% |
| `LuckSiege/Keyboard` | 2017-03-06 00:00:00 | 7 | 4.455 | 85.7% | 85.7% | 14.3% | 100.0% | 100.0% |
| `sindresorhus/path-key` | 2016-01-18 00:00:00 | 8 | 4.447 | 75.0% | 75.0% | 37.5% | 100.0% | 100.0% |
| `sindresorhus/normalize-newline-cli` | 2016-01-18 00:00:00 | 11 | 4.447 | 90.9% | 81.8% | 63.6% | 100.0% | 100.0% |
| `ethereumjs/geth.js` | 2016-01-18 00:00:00 | 5 | 4.447 | 80.0% | 80.0% | 20.0% | 100.0% | 100.0% |
| `ChienDevIT/cleave.js` | 2019-04-15 00:00:00 | 5 | 4.439 | 100.0% | 100.0% | 40.0% | 100.0% | 100.0% |
| `brianbartolini/startup_landing_page` | 2016-02-08 00:00:00 | 8 | 4.427 | 100.0% | 87.5% | 62.5% | 100.0% | 100.0% |
| `dchrastil/TTSL` | 2017-06-12 00:00:00 | 7 | 4.426 | 57.1% | 71.4% | 28.6% | 100.0% | 100.0% |
| `Naituw/GraphicsSmoothTest` | 2018-05-14 00:00:00 | 17 | 4.416 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| `ChienDevIT/dayjs` | 2019-04-01 00:00:00 | 5 | 4.411 | 100.0% | 100.0% | 80.0% | 100.0% | 100.0% |
| `ChienDevIT/tmux` | 2019-04-01 00:00:00 | 6 | 4.411 | 100.0% | 100.0% | 50.0% | 100.0% | 100.0% |
| `ChienDevIT/babel` | 2019-04-01 00:00:00 | 6 | 4.411 | 100.0% | 100.0% | 50.0% | 100.0% | 100.0% |
| `ChienDevIT/assemblyscript` | 2019-04-01 00:00:00 | 9 | 4.411 | 100.0% | 100.0% | 44.4% | 100.0% | 100.0% |
| `ChienDevIT/foundationdb` | 2019-04-01 00:00:00 | 9 | 4.411 | 100.0% | 100.0% | 44.4% | 100.0% | 100.0% |
| `b3none/steam-group-members` | 2019-04-01 00:00:00 | 5 | 4.411 | 60.0% | 100.0% | 40.0% | 100.0% | 100.0% |
| `shantamsultania/Motion-Detection-System` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Doctor-computer-vision` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/greyatom-python-for-data-science` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/portfolio-website` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Cloud-Titans-` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/RecyclerView-using-kotlin` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/WebScrapping-using-python-examples` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Templete-appointment-schedular` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Triviapplication-in-Kotlin` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/JSON-application-in-kotlin` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Kotlin_example` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Facial-Detection-System` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/webview_application_kotlin` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/sending-emails-using-python` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/TextScanner-Android-application` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/webhookrepo` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Template-for-portfolio` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Car-detection-System` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Notifiacation-app-using-kotlin` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `shantamsultania/Pythonbasics` | 2020-06-08 00:00:00 | 5 | 4.410 | 80.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `VakinduPhilliam/Python_Crypt_Routine` | 2019-06-03 00:00:00 | 5 | 4.409 | 60.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `VakinduPhilliam/Python_Synchronization_Primitives` | 2019-06-03 00:00:00 | 5 | 4.409 | 60.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `VakinduPhilliam/Python_Snippet_Trace` | 2019-06-03 00:00:00 | 5 | 4.409 | 60.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `VakinduPhilliam/Python_File_IO` | 2019-06-03 00:00:00 | 5 | 4.409 | 60.0% | 80.0% | 60.0% | 100.0% | 100.0% |
| `VakinduPhilliam/Python_Signal_Pipeline` | 2019-06-03 00:00:00 | 5 | 4.409 | 60.0% | 80.0% | 60.0% | 100.0% | 100.0% |

Noticeable clusters include self-starring catalogs (e.g. `shantamsultania/*` starring 20 identical repositories in a single day with 100% burst and 80% inactive accounts) and mirror spam (`ChienDevIT/*`).
