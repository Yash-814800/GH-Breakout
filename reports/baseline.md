# Baseline evaluation (Phase 6)

Every later model must beat **B1** on PR-AUC and precision@k to be promoted.

## Setup

- Candidates: age <= 90 d, < 200 stars before D, >= 5 stars in [D-14, D), no forks / mirrors / bot owners.
- Label (primary): `breakout_rel` = 30-day gain >= max(100, 0.995 quantile of the candidates on that snapshot).
- Rolling-origin, expanding window: test blocks of 3 months, first block after 2 years, embargo 30 days. 29 folds; test snapshots 2018-02-01 .. 2025-05-01.
- Data: GH Archive trusted era (events before 2025-05-24).
- Confidence intervals: block bootstrap over snapshot dates (1000 resamples, blocks of 4 weeks).
- precision@k = hits in top k / k per snapshot, averaged over all snapshots; recall@k and AP are averaged over snapshots with at least one positive. Ties are broken by repo_id.

Baselines:

- **B1**: stars in the last 7 days (ties: last day)
- **B2**: 7-day stars / (stars so far + 10)
- **B3**: 7-day stars minus the 7 days before

## Folds

| fold | test_start | test_end | train_snaps | test_snaps | test_pos | B1 PR-AUC | B1 P@25 | B2 PR-AUC | B2 P@25 | B3 PR-AUC | B3 P@25 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2018-02-01 | 2018-05-01 | 105 | 13 | 326 | 0.039 | 0.077 | 0.035 | 0.068 | 0.035 | 0.068 |
| 1 | 2018-05-01 | 2018-08-01 | 117 | 13 | 295 | 0.053 | 0.123 | 0.041 | 0.098 | 0.046 | 0.114 |
| 2 | 2018-08-01 | 2018-11-01 | 131 | 13 | 276 | 0.050 | 0.105 | 0.046 | 0.102 | 0.047 | 0.108 |
| 3 | 2018-11-01 | 2019-02-01 | 144 | 13 | 274 | 0.051 | 0.111 | 0.046 | 0.108 | 0.048 | 0.102 |
| 4 | 2019-02-01 | 2019-05-01 | 157 | 13 | 349 | 0.043 | 0.098 | 0.037 | 0.108 | 0.039 | 0.095 |
| 5 | 2019-05-01 | 2019-08-01 | 170 | 13 | 360 | 0.054 | 0.111 | 0.039 | 0.092 | 0.045 | 0.111 |
| 6 | 2019-08-01 | 2019-11-01 | 183 | 13 | 332 | 0.058 | 0.135 | 0.044 | 0.111 | 0.049 | 0.132 |
| 7 | 2019-11-01 | 2020-02-01 | 196 | 13 | 313 | 0.045 | 0.114 | 0.037 | 0.092 | 0.042 | 0.123 |
| 8 | 2020-02-01 | 2020-05-01 | 209 | 13 | 386 | 0.045 | 0.111 | 0.033 | 0.089 | 0.039 | 0.102 |
| 9 | 2020-05-01 | 2020-08-01 | 222 | 13 | 462 | 0.051 | 0.126 | 0.036 | 0.108 | 0.043 | 0.126 |
| 10 | 2020-08-01 | 2020-11-01 | 235 | 13 | 392 | 0.077 | 0.175 | 0.060 | 0.166 | 0.066 | 0.154 |
| 11 | 2020-11-01 | 2021-02-01 | 248 | 13 | 366 | 0.054 | 0.114 | 0.041 | 0.102 | 0.046 | 0.105 |
| 12 | 2021-02-01 | 2021-05-01 | 261 | 13 | 385 | 0.055 | 0.145 | 0.044 | 0.126 | 0.048 | 0.151 |
| 13 | 2021-05-01 | 2021-08-01 | 274 | 13 | 366 | 0.060 | 0.126 | 0.046 | 0.129 | 0.050 | 0.126 |
| 14 | 2021-08-01 | 2021-11-01 | 287 | 13 | 321 | 0.053 | 0.114 | 0.042 | 0.092 | 0.045 | 0.105 |
| 15 | 2021-11-01 | 2022-02-01 | 300 | 14 | 394 | 0.047 | 0.120 | 0.041 | 0.120 | 0.043 | 0.123 |
| 16 | 2022-02-01 | 2022-05-01 | 313 | 12 | 379 | 0.051 | 0.120 | 0.039 | 0.113 | 0.042 | 0.123 |
| 17 | 2022-05-01 | 2022-08-01 | 326 | 13 | 391 | 0.058 | 0.126 | 0.043 | 0.117 | 0.049 | 0.126 |
| 18 | 2022-08-01 | 2022-11-01 | 339 | 14 | 510 | 0.065 | 0.166 | 0.053 | 0.163 | 0.056 | 0.160 |
| 19 | 2022-11-01 | 2023-02-01 | 352 | 13 | 504 | 0.049 | 0.135 | 0.030 | 0.117 | 0.039 | 0.117 |
| 20 | 2023-02-01 | 2023-05-01 | 366 | 12 | 670 | 0.017 | 0.037 | 0.011 | 0.040 | 0.012 | 0.040 |
| 21 | 2023-05-01 | 2023-08-01 | 378 | 14 | 1040 | 0.018 | 0.080 | 0.012 | 0.051 | 0.013 | 0.071 |
| 22 | 2023-08-01 | 2023-11-01 | 391 | 13 | 546 | 0.027 | 0.114 | 0.018 | 0.117 | 0.022 | 0.114 |
| 23 | 2023-11-01 | 2024-02-01 | 405 | 13 | 514 | 0.039 | 0.098 | 0.026 | 0.083 | 0.030 | 0.098 |
| 24 | 2024-02-01 | 2024-05-01 | 418 | 13 | 727 | 0.028 | 0.071 | 0.019 | 0.062 | 0.022 | 0.071 |
| 25 | 2024-05-01 | 2024-08-01 | 431 | 13 | 731 | 0.019 | 0.049 | 0.013 | 0.043 | 0.015 | 0.049 |
| 26 | 2024-08-01 | 2024-11-01 | 444 | 13 | 545 | 0.024 | 0.034 | 0.017 | 0.034 | 0.019 | 0.031 |
| 27 | 2024-11-01 | 2025-02-01 | 457 | 13 | 580 | 0.040 | 0.086 | 0.027 | 0.077 | 0.033 | 0.083 |
| 28 | 2025-02-01 | 2025-05-01 | 470 | 12 | 824 | 0.031 | 0.133 | 0.020 | 0.113 | 0.024 | 0.127 |

## Pooled test metrics (all folds)

| baseline | PR-AUC [95% CI] | ROC-AUC | mean AP | P@10 | P@25 | P@50 | R@10 | R@25 | R@50 |
|---|---|---|---|---|---|---|---|---|---|
| B1 | 0.0286 [0.0246, 0.0345] | 0.8157 | 0.063 [0.058, 0.068] | 0.129 [0.115, 0.143] | 0.109 [0.100, 0.118] | 0.086 [0.080, 0.092] | 0.044 | 0.090 | 0.139 |
| B2 | 0.0197 [0.0168, 0.0240] | 0.7409 | 0.052 [0.047, 0.056] | 0.125 [0.112, 0.138] | 0.098 [0.089, 0.107] | 0.078 [0.072, 0.083] | 0.042 | 0.081 | 0.128 |
| B3 | 0.0227 [0.0191, 0.0279] | 0.7108 | 0.056 [0.051, 0.060] | 0.126 [0.112, 0.139] | 0.105 [0.097, 0.114] | 0.083 [0.077, 0.089] | 0.043 | 0.087 | 0.136 |

Test rows 2,667,524, positives 13,558 (positive rate 0.5083%).

### Calibration of B1 (isotonic, fitted on each fold's training dates)

Brier 0.00501, log loss 0.02808, ECE (10 quantile bins) 0.00071.

## Per year (mean over the year's test snapshots)

**B1**

| year | n_snapshots | ap | precision@10 | precision@25 | precision@50 |
|---|---|---|---|---|---|
| 2018 | 48 | 0.069 | 0.131 | 0.102 | 0.076 |
| 2019 | 52 | 0.070 | 0.158 | 0.116 | 0.087 |
| 2020 | 52 | 0.073 | 0.140 | 0.132 | 0.106 |
| 2021 | 52 | 0.075 | 0.162 | 0.123 | 0.092 |
| 2022 | 52 | 0.078 | 0.165 | 0.143 | 0.113 |
| 2023 | 52 | 0.042 | 0.088 | 0.085 | 0.063 |
| 2024 | 53 | 0.036 | 0.058 | 0.055 | 0.057 |
| 2025 | 16 | 0.054 | 0.144 | 0.133 | 0.106 |

**B2**

| year | n_snapshots | ap | precision@10 | precision@25 | precision@50 |
|---|---|---|---|---|---|
| 2018 | 48 | 0.061 | 0.131 | 0.093 | 0.072 |
| 2019 | 52 | 0.061 | 0.144 | 0.102 | 0.081 |
| 2020 | 52 | 0.060 | 0.140 | 0.116 | 0.093 |
| 2021 | 52 | 0.063 | 0.154 | 0.114 | 0.088 |
| 2022 | 52 | 0.065 | 0.158 | 0.133 | 0.103 |
| 2023 | 52 | 0.031 | 0.092 | 0.075 | 0.055 |
| 2024 | 53 | 0.027 | 0.057 | 0.052 | 0.049 |
| 2025 | 16 | 0.038 | 0.125 | 0.107 | 0.089 |

**B3**

| year | n_snapshots | ap | precision@10 | precision@25 | precision@50 |
|---|---|---|---|---|---|
| 2018 | 48 | 0.064 | 0.127 | 0.096 | 0.078 |
| 2019 | 52 | 0.064 | 0.152 | 0.115 | 0.086 |
| 2020 | 52 | 0.066 | 0.144 | 0.122 | 0.104 |
| 2021 | 52 | 0.067 | 0.158 | 0.123 | 0.089 |
| 2022 | 52 | 0.069 | 0.154 | 0.140 | 0.109 |
| 2023 | 52 | 0.034 | 0.092 | 0.082 | 0.060 |
| 2024 | 53 | 0.030 | 0.053 | 0.055 | 0.052 |
| 2025 | 16 | 0.045 | 0.131 | 0.125 | 0.096 |

## Lead time versus GitHub Trending

Population: repos that appeared on an all-languages GitHub Trending list within 60 days of a test snapshot whose window has Trending coverage (>= 54 of 60 days). First flag = earliest snapshot in which the repo ranked in the top 25; snapshot resolution is weekly, so a flag is visible at most 7 days late. Positive lead = we flagged before Trending; a repo flagged only after it trended counts as not early.

| baseline | trending repos | flagged (top-25) | never flagged | flagged before Trending | >= 7 d before | median lead (d) | IQR (d) |
|---|---|---|---|---|---|---|---|
| B1 | 3053 | 608 | 0.801 | 0.088 | 0.034 | 0.0 | 0.0 .. 2.0 |
| B2 | 3053 | 489 | 0.840 | 0.091 | 0.032 | 1.0 | 0.0 .. 4.0 |
| B3 | 3053 | 551 | 0.820 | 0.087 | 0.032 | 0.0 | 0.0 .. 2.0 |

## Figures

![PR curve](figures/baseline_pr_curve.png)

![precision by year](figures/baseline_precision_by_year.png)

## Sanity check: top 10 B1-ranked candidates on three historical dates

`gain_30d` is the realized gain in [D, D+30); `label` is `breakout_rel`.

**2019-11-25**

| repo_name_at_D | stars_7d | stars_1d | stars_total_before | gain_30d | label |
|---|---|---|---|---|---|
| psliwka/vim-smoothie | 199 | 2 | 199 | 30 | False |
| Tencent/wwsearch | 195 | 2 | 195 | 48 | False |
| wei-tim/YOWO | 192 | 6 | 194 | 85 | False |
| connor4312/cockatiel | 177 | 112 | 177 | 610 | True |
| opheron/electric-hive-learning-guide | 174 | 5 | 174 | 13 | False |
| khstangherlin/monker | 162 | 1 | 162 | 6 | False |
| alirezadir/Production-Level-Deep-Learning | 161 | 90 | 161 | 1603 | True |
| fuzzitdev/javafuzz | 143 | 5 | 143 | 18 | False |
| heybourn/headwind | 142 | 6 | 142 | 33 | False |
| replicatedhq/kotsadm | 137 | 0 | 137 | 11 | False |

**2021-09-13**

| repo_name_at_D | stars_7d | stars_1d | stars_total_before | gain_30d | label |
|---|---|---|---|---|---|
| ghealer/GUI_Tools | 198 | 5 | 198 | 151 | False |
| 0voice/Understanding_in_Rust | 191 | 5 | 192 | 166 | False |
| Uahh/slscq | 182 | 32 | 182 | 166 | False |
| antfu/github-doorcat | 172 | 5 | 172 | 36 | False |
| vuejs/repl | 172 | 3 | 172 | 34 | False |
| fishfight/FishFight | 167 | 2 | 173 | 37 | False |
| peng-zhihui/OpenHeat | 165 | 79 | 171 | 157 | False |
| rails/jsbundling-rails | 164 | 12 | 164 | 76 | False |
| ventusff/neurecon | 163 | 10 | 163 | 89 | False |
| threathunters-io/laurel | 154 | 2 | 154 | 44 | False |

**2024-03-25**

| repo_name_at_D | stars_7d | stars_1d | stars_total_before | gain_30d | label |
|---|---|---|---|---|---|
| jarvis2f/vortex | 199 | 14 | 199 | 63 | False |
| mlecauchois/micrograd-cuda | 195 | 5 | 196 | 8 | False |
| wzy-99/the-finals-app | 195 | 0 | 195 | 0 | False |
| tortuc/WinRAR-CRACKED | 193 | 0 | 193 | 0 | False |
| Sharon-Harper/Mdrkjg4 | 193 | 0 | 193 | 0 | False |
| Wuu-Ce/rust-app | 192 | 31 | 192 | 1 | False |
| Riddhi-5/CANVA-FULL-VERSION-2024 | 192 | 1 | 192 | 0 | False |
| Sandra-Williams/czb2la26 | 191 | 0 | 191 | 4 | False |
| pepedeveloper007/PEPE-BOT | 190 | 0 | 190 | 0 | False |
| Amanda-Howard98/Jdh32hs | 185 | 0 | 185 | 0 | False |

