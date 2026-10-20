# Training/Serving Parity Report (2024-06-03)

**Date Evaluated:** `2024-06-03`
**Status:** PASS
**Champion Model:** `20261019-b5ff585`

## Summary Metrics
- **Candidate Jaccard Index:** 1.0000 (Required: >= 0.99) -> PASS
- **Historical Candidates:** 12434
- **Window Mode Candidates:** 12434
- **Common Candidates:** 12434
- **Overall Cell Match Rate:** 0.9999 (Required: >= 0.99) -> PASS
- **Spearman Rank Correlation:** 0.9999 (Required: >= 0.99) -> PASS

## Per-Feature Match Rates
| Feature | Match Rate | Status |
|---|---:|---|
| `actor_days_14d` | 100.00% | PASS |
| `age_days` | 100.00% | PASS |
| `birth_from_public_event` | 100.00% | PASS |
| `comment_events_14d` | 100.00% | PASS |
| `core_actor_count_90d` | 100.00% | PASS |
| `days_api_created_to_birth` | 100.00% | PASS |
| `days_since_first_star` | 100.00% | PASS |
| `days_since_last_release` | 99.99% | PASS |
| `detail_coverage_28d` | 100.00% | PASS |
| `distinct_contributors_28d` | 100.00% | PASS |
| `distinct_pushers_28d` | 100.00% | PASS |
| `distinct_session_actors_28d` | 100.00% | PASS |
| `era_post_2025_10` | 100.00% | PASS |
| `event_type_entropy_14d` | 100.00% | PASS |
| `external_pr_authors_28d` | 100.00% | PASS |
| `first_time_contributor_rate_28d` | 100.00% | PASS |
| `fork_star_ratio_14d` | 100.00% | PASS |
| `forks_14d` | 100.00% | PASS |
| `forks_7d` | 100.00% | PASS |
| `hn_any_before` | 100.00% | PASS |
| `hn_max_points_aged` | 100.00% | PASS |
| `hn_stories_before_14d` | 100.00% | PASS |
| `hn_stories_before_3d` | 100.00% | PASS |
| `issue_close_ratio_28d` | 100.00% | PASS |
| `issue_events_14d` | 100.00% | PASS |
| `issues_closed_28d` | 100.00% | PASS |
| `issues_opened_28d` | 100.00% | PASS |
| `median_first_response_hours_28d` | 100.00% | PASS |
| `median_merge_hours_28d` | 100.00% | PASS |
| `median_session_minutes_28d` | 100.00% | PASS |
| `new_contributors_28d` | 100.00% | PASS |
| `owner_prior_breakouts` | 99.20% | PASS |
| `owner_prior_repos_seen` | 100.00% | PASS |
| `owner_type` | 100.00% | PASS |
| `pr_events_14d` | 100.00% | PASS |
| `primary_language` | 100.00% | PASS |
| `prs_merged_28d` | 100.00% | PASS |
| `prs_opened_28d` | 100.00% | PASS |
| `push_active_days_14d` | 100.00% | PASS |
| `releases_total_before` | 99.99% | PASS |
| `reviews_14d` | 100.00% | PASS |
| `sessions_28d` | 100.00% | PASS |
| `sg_median_account_age_days` | 100.00% | PASS |
| `sg_median_stars_same_day` | 100.00% | PASS |
| `sg_n` | 100.00% | PASS |
| `sg_retention_any_28d` | 100.00% | PASS |
| `sg_retention_fork_28d` | 100.00% | PASS |
| `sg_retention_issue_or_pr_28d` | 100.00% | PASS |
| `sg_share_account_lt_30d` | 100.00% | PASS |
| `sg_share_bulk_starrers` | 100.00% | PASS |
| `sg_share_experienced` | 100.00% | PASS |
| `sg_share_zero_prior_activity` | 100.00% | PASS |
| `sg_tm_known_share_14d` | 100.00% | PASS |
| `sg_tm_max_14d` | 100.00% | PASS |
| `sg_tm_mean_14d` | 100.00% | PASS |
| `sg_tm_top_count_14d` | 100.00% | PASS |
| `share_issues_responded_48h` | 100.00% | PASS |
| `star_accel_7d` | 100.00% | PASS |
| `star_active_days_14d` | 100.00% | PASS |
| `star_gini_14d` | 100.00% | PASS |
| `star_max_day_share_14d` | 100.00% | PASS |
| `star_max_hour_share_7d` | 100.00% | PASS |
| `star_ratio_7d` | 100.00% | PASS |
| `stars_14d` | 100.00% | PASS |
| `stars_1d` | 100.00% | PASS |
| `stars_28d` | 100.00% | PASS |
| `stars_3d` | 100.00% | PASS |
| `stars_7d` | 100.00% | PASS |
| `stars_total_before` | 100.00% | PASS |
| `tags_created_total_before` | 99.99% | PASS |
| `top_actor_share_28d` | 100.00% | PASS |

## Discrepancies
- None (100% of tested feature cells match parity requirements).

## Methodology Notes
- Historical features were produced by `mart_repo_features` in history mode.
- Daily window features were produced with persistent state tables (`tastemaker_state.parquet`, `owner_state.parquet`, `tastemaker_thresholds.parquet`) plus incremental window aggregation.
- Predictions scored with the current champion model and compared via Spearman rank correlation.
