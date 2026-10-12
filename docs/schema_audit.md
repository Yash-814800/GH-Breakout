# Payload schema audit

Generated 2026-10-12 by `breakout ingest audit`. Source: one hour (12:00 UTC) of
GH Archive for each sampled day below. Presence % = share of that type's events in the
sample hour where the JSON path exists and is not null. Paths are listed to depth 3
below `payload`. A `—` means the type had zero events in that sample hour.
**Samples are one hour each; small types (PublicEvent, ReleaseEvent) can have very few
rows, check the count row.**

Legend: ⚠ = presence ≥ 50% before 2025-10-07 and < 50% after (GitHub payload trimming).

## Sampled hours

| day (12:00 UTC) | lines | bad lines | WatchEvent | ForkEvent | IssuesEvent | IssueCommentEvent | PullRequestEvent | PullRequestReviewEvent | ReleaseEvent | CreateEvent | PublicEvent | PushEvent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015-03-02 | 23,766 | 0 | 2,108 | 748 | 1,152 | 2,158 | 1,118 | 0 | 96 | 2,518 | 26 | 12,449 |
| 2016-06-01 | 45,671 | 0 | 3,602 | 1,342 | 1,944 | 3,927 | 2,733 | 0 | 164 | 5,991 | 17 | 23,396 |
| 2018-06-01 | 64,527 | 0 | 4,364 | 1,598 | 2,388 | 4,768 | 3,868 | 0 | 238 | 8,443 | 72 | 35,241 |
| 2020-06-01 | 119,800 | 0 | 6,719 | 2,325 | 3,648 | 8,681 | 12,003 | 0 | 450 | 19,120 | 359 | 58,390 |
| 2022-06-01 | 173,954 | 0 | 4,604 | 1,527 | 2,217 | 7,885 | 40,702 | 3,487 | 572 | 45,066 | 356 | 59,270 |
| 2024-06-03 | 273,532 | 0 | 8,154 | 2,006 | 5,922 | 11,213 | 17,884 | 6,500 | 1,277 | 38,096 | 760 | 168,238 |
| 2025-09-01 | 166,609 | 0 | 4,653 | 1,236 | 2,637 | 6,581 | 14,797 | 3,924 | 800 | 21,704 | 484 | 101,718 |
| 2025-11-03 | 159,464 | 0 | 2,967 | 684 | 2,772 | 3,791 | 8,222 | 2,359 | 450 | 13,499 | 81 | 117,207 |
| 2026-10-10 | 40,599 | 0 | 346 | 87 | 709 | 926 | 1,649 | 351 | 324 | 3,732 | 8 | 30,564 |

## Fields dropping below 50% after 2025-10-07

- **ForkEvent**: `payload.forkee.public`
- **IssuesEvent**: `payload.issue.author_association`, `payload.issue.closed_at`, `payload.issue.state_reason`
- **IssueCommentEvent**: `payload.comment.author_association`, `payload.issue.author_association`
- **PullRequestEvent**: `payload.pull_request._links`, `payload.pull_request._links.comments`, `payload.pull_request._links.commits`, `payload.pull_request._links.html`, `payload.pull_request._links.issue`, `payload.pull_request._links.review_comment`, `payload.pull_request._links.review_comments`, `payload.pull_request._links.self`, `payload.pull_request._links.statuses`, `payload.pull_request.additions`, `payload.pull_request.assignees`, `payload.pull_request.author_association`, `payload.pull_request.base.label`, `payload.pull_request.base.user`, `payload.pull_request.body`, `payload.pull_request.changed_files`, `payload.pull_request.comments`, `payload.pull_request.comments_url`, `payload.pull_request.commits`, `payload.pull_request.commits_url`, `payload.pull_request.created_at`, `payload.pull_request.deletions`, `payload.pull_request.diff_url`, `payload.pull_request.draft`, `payload.pull_request.head.label`, `payload.pull_request.head.user`, `payload.pull_request.html_url`, `payload.pull_request.issue_url`, `payload.pull_request.labels`, `payload.pull_request.locked`, `payload.pull_request.maintainer_can_modify`, `payload.pull_request.merge_commit_sha`, `payload.pull_request.mergeable_state`, `payload.pull_request.merged`, `payload.pull_request.node_id`, `payload.pull_request.patch_url`, `payload.pull_request.requested_reviewers`, `payload.pull_request.requested_teams`, `payload.pull_request.review_comment_url`, `payload.pull_request.review_comments`, `payload.pull_request.review_comments_url`, `payload.pull_request.state`, `payload.pull_request.statuses_url`, `payload.pull_request.title`, `payload.pull_request.updated_at`, `payload.pull_request.user`, `payload.pull_request.user.avatar_url`, `payload.pull_request.user.events_url`, `payload.pull_request.user.followers_url`, `payload.pull_request.user.following_url`, `payload.pull_request.user.gists_url`, `payload.pull_request.user.gravatar_id`, `payload.pull_request.user.html_url`, `payload.pull_request.user.id`, `payload.pull_request.user.login`, `payload.pull_request.user.node_id`, `payload.pull_request.user.organizations_url`, `payload.pull_request.user.received_events_url`, `payload.pull_request.user.repos_url`, `payload.pull_request.user.site_admin`, `payload.pull_request.user.starred_url`, `payload.pull_request.user.subscriptions_url`, `payload.pull_request.user.type`, `payload.pull_request.user.url`, `payload.pull_request.user.user_view_type`
- **PullRequestReviewEvent**: `payload.pull_request._links`, `payload.pull_request._links.comments`, `payload.pull_request._links.commits`, `payload.pull_request._links.html`, `payload.pull_request._links.issue`, `payload.pull_request._links.review_comment`, `payload.pull_request._links.review_comments`, `payload.pull_request._links.self`, `payload.pull_request._links.statuses`, `payload.pull_request.assignees`, `payload.pull_request.author_association`, `payload.pull_request.base.label`, `payload.pull_request.base.user`, `payload.pull_request.body`, `payload.pull_request.comments_url`, `payload.pull_request.commits_url`, `payload.pull_request.created_at`, `payload.pull_request.diff_url`, `payload.pull_request.draft`, `payload.pull_request.head.label`, `payload.pull_request.head.user`, `payload.pull_request.html_url`, `payload.pull_request.issue_url`, `payload.pull_request.labels`, `payload.pull_request.locked`, `payload.pull_request.merge_commit_sha`, `payload.pull_request.node_id`, `payload.pull_request.patch_url`, `payload.pull_request.requested_reviewers`, `payload.pull_request.requested_teams`, `payload.pull_request.review_comment_url`, `payload.pull_request.review_comments_url`, `payload.pull_request.state`, `payload.pull_request.statuses_url`, `payload.pull_request.title`, `payload.pull_request.updated_at`, `payload.pull_request.user`, `payload.pull_request.user.avatar_url`, `payload.pull_request.user.events_url`, `payload.pull_request.user.followers_url`, `payload.pull_request.user.following_url`, `payload.pull_request.user.gists_url`, `payload.pull_request.user.gravatar_id`, `payload.pull_request.user.html_url`, `payload.pull_request.user.id`, `payload.pull_request.user.login`, `payload.pull_request.user.node_id`, `payload.pull_request.user.organizations_url`, `payload.pull_request.user.received_events_url`, `payload.pull_request.user.repos_url`, `payload.pull_request.user.site_admin`, `payload.pull_request.user.starred_url`, `payload.pull_request.user.subscriptions_url`, `payload.pull_request.user.type`, `payload.pull_request.user.url`, `payload.pull_request.user.user_view_type`, `payload.review.author_association`
- **PushEvent**: `payload.commits`, `payload.distinct_size`, `payload.size`

## Data-volume observations (manual probe, 2026-10-12)

The sample table above shows WatchEvent (stars) rows per sampled hour falling from 4,653
(2025-09-01) to 2,967 (2025-11-03) to 346 (2026-10-10), while PushEvent, CreateEvent and
PullRequestEvent stay in the same range. Extra probes of the 12:00 UTC hour (events counted
straight from the public hourly files with `grep`, not through the parser):

| day | WatchEvent | IssuesEvent | ForkEvent |
|---|---:|---:|---:|
| 2025-09-15 | 4,447 | 2,215 | 1,112 |
| 2025-10-08 | 4,532 | 2,638 | 1,165 |
| 2025-11-15 | 3,519 | 3,142 | 840 |
| 2025-12-15 | 2,297 | 2,111 | 514 |
| 2026-02-15 | 3,264 | 2,869 | 703 |
| 2026-04-15 | 872 | 1,014 | 176 |
| 2026-06-15 | 119 | 127 | 28 |
| 2026-08-15 | 24 | 31 | 5 |
| 2026-09-15 | 1,158 | 2,052 | 248 |
| 2026-10-10 | 346 | 709 | 87 |

2026-08-15 stays at roughly 17-42 WatchEvents in *every* hour of the day, so this is a property
of the archived stream, not of one bad file. Whole-archive star events are therefore far sparser
since about 2026-03 than the model's label and candidate definitions assume. This must be
resolved (or the label/candidate thresholds re-derived) before any modeling on post-2026-03 data.

## Parser decisions

All paths below were verified against the sampled hours above (presence % per era, in sample
order 2015 / 2016 / 2018 / 2020 / 2022 / 2024 / 2025-09 / 2025-11 / 2026-10). "Post-trim" means
2025-11-03 and 2026-10-10. A path that is absent in an era yields NULL; nothing is imputed.
No era-specific path fallbacks were needed beyond the `COALESCE`s listed here.

| column | JSON path(s) used | availability across eras | downstream features affected |
|---|---|---|---|
| `event_id` | `id` (string of digits, `TRY_CAST` to BIGINT) | all eras; rows that fail are dropped and counted as `bad_ids` | none |
| `created_at` | `created_at` (ISO-8601 `Z`) -> naive UTC `TIMESTAMP` | all eras | all (point-in-time cut) |
| `repo_id`, `repo_name` | `repo.id`, `repo.name` | all eras. A very small number of events have `repo: {}` (seen 2026-10-10, ForkEvent); they are dropped and counted in `bad_ids` | all |
| `actor_id`, `actor_login` | `actor.id`, `actor.login` | all eras | tastemaker / stargazer features |
| `org_id` | `org.id` | present on only ~28-41% of events in every era (genuinely nullable) | owner-type proxy |
| `action` | `payload.action` for Watch / Issues / IssueComment / PullRequest / PullRequestReview / Release | 100% in every era where the type exists (PullRequestReviewEvent only from the 2022 sample on). `ForkEvent.payload.action` is 0% until 2025-11 and is deliberately not extracted | issue/PR open and close counts |
| `number` | Issues/IssueComment: `payload.issue.number`; PullRequest: `COALESCE(payload.pull_request.number, payload.number)`; Review: same | 100% wherever the type exists; `payload.number` is absent on review events, `payload.pull_request.number` covers it | issue/PR de-duplication |
| `is_pull_request` | PullRequest/Review events: TRUE; IssuesEvent: FALSE (GitHub never emits IssuesEvent for a PR; `payload.issue.pull_request` is 0% on those); IssueCommentEvent: `payload.issue.pull_request` is present and non-null | PR-comment share is 35% (2015) rising to 65-72% (2022+); stable across the trim | PR vs issue discussion features |
| `target_user_id` | `payload.issue.user.id` / `payload.pull_request.user.id` | issues/comments: 100% all eras. **PR and review events: 100% until 2025-09, 0% post-trim** | "external contributor" and maintainer-reply features lose PR authorship after 2025-10-07 |
| `target_created_at` | `payload.issue.created_at` / `payload.pull_request.created_at` | issues/comments: 100% all eras. **PR and review events: 0% post-trim** | issue/PR response-time features for PRs |
| `pr_merged` | `payload.pull_request.merged` only when `payload.action = 'closed'` (PullRequestEvent) | 100% until 2025-09, **0% post-trim** | merged-PR count features are not computable after 2025-10-07 |
| `review_state` | `payload.review.state` | 100% wherever the type exists (all eras incl. post-trim) | review activity features |
| `ref_type` | `payload.ref_type` (CreateEvent) | 100% all eras | repo birth detection (`repository`), branch/tag counts |
| `forkee_repo_id` | `payload.forkee.id` (ForkEvent) | 100% all eras | fork-graph features |
| `release_prerelease` | `payload.release.prerelease` (ReleaseEvent) | 100% all eras | release cadence features |
| `push_daily` | PushEvent: `repo.id`, `actor.id`, `created_at`, `repo.name` only (no payload field used) | all eras. `payload.commits`, `payload.size` and `payload.distinct_size` vanish post-trim and are never used | commit counts per push are NOT available; only push counts |

Fields that GitHub trimmed on 2025-10-07 and that we therefore never rely on:
`author_association` (issue / comment / PR), `pull_request.user`, `pull_request.merged`,
`pull_request.created_at`, `_links`, push `commits` / `size` / `distinct_size`.

## WatchEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 2,108 | 3,602 | 4,364 | 6,719 | 4,604 | 8,154 | 4,653 | 2,967 | 346 |
| `payload.action` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

## ForkEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 748 | 1,342 | 1,598 | 2,325 | 1,527 | 2,006 | 1,236 | 684 | 87 |
| `payload.action` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 |
| `payload.forkee` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.allow_forking` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.archive_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.archived` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.assignees_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.blobs_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.branches_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.clone_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.collaborators_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.comments_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.commits_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.compare_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.contents_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.contributors_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.created_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.default_branch` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.deployments_url` | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.description` | 97 | 98 | 83 | 82 | 75 | 73 | 74 | 74 | 82 |
| `payload.forkee.disabled` | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.downloads_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.fork` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.forks` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.forks_count` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.forks_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.full_name` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.git_commits_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.git_refs_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.git_tags_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.git_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_discussions` | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_downloads` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_issues` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_pages` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_projects` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.has_pull_requests` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 |
| `payload.forkee.has_wiki` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.homepage` | 53 | 54 | 55 | 56 | 54 | 57 | 59 | 57 | 69 |
| `payload.forkee.hooks_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.is_template` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.issue_comment_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.issue_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.issues_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.keys_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.labels_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.language` | 17 | 6 | 0 | 0 | 0 | 0 | 0 | 7 | 2 |
| `payload.forkee.languages_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.license` | 0 | 0 | 7 | 46 | 54 | 8 | 58 | 58 | 72 |
| `payload.forkee.license.key` | 0 | 0 | 7 | 46 | 54 | 8 | 58 | 58 | 72 |
| `payload.forkee.license.name` | 0 | 0 | 7 | 46 | 54 | 8 | 58 | 58 | 72 |
| `payload.forkee.license.node_id` | 0 | 0 | 7 | 46 | 54 | 8 | 58 | 58 | 72 |
| `payload.forkee.license.spdx_id` | 0 | 0 | 6 | 46 | 54 | 8 | 58 | 58 | 72 |
| `payload.forkee.license.url` | 0 | 0 | 6 | 36 | 46 | 6 | 50 | 50 | 61 |
| `payload.forkee.merges_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.milestones_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.name` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.notifications_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.open_issues` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.open_issues_count` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.avatar_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.followers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.following_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.gists_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.gravatar_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.login` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.organizations_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.received_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.repos_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.site_admin` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.starred_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.subscriptions_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.owner.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.forkee.private` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.public` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.forkee.pull_request_creation_policy` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 |
| `payload.forkee.pulls_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.pushed_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.releases_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.size` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.ssh_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.stargazers_count` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.stargazers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.statuses_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.subscribers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.subscription_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.svn_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.tags_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.teams_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.topics` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.trees_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.updated_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.visibility` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.watchers` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.watchers_count` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.forkee.web_commit_signoff_required` | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 |

## IssuesEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 1,152 | 1,944 | 2,388 | 3,648 | 2,217 | 5,922 | 2,637 | 2,772 | 709 |
| `payload.action` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.assignee` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.avatar_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.events_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.followers_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.following_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.gists_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.gravatar_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.html_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.login` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.organizations_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.received_events_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.repos_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.site_admin` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.starred_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.subscriptions_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.type` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignee.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.assignees` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 5 |
| `payload.issue` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.active_lock_reason` | 0 | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 |
| `payload.issue.assignee` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.avatar_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.events_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.followers_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.following_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.gists_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.gravatar_id` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.html_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.id` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.login` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.node_id` | 0 | 0 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.organizations_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.received_events_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.repos_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.site_admin` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.starred_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.subscriptions_url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.type` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.url` | 20 | 16 | 17 | 16 | 20 | 16 | 23 | 40 | 15 |
| `payload.issue.assignee.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 23 | 40 | 15 |
| `payload.issue.assignees` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.author_association` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.issue.body` | 98 | 98 | 99 | 99 | 81 | 89 | 90 | 90 | 98 |
| `payload.issue.closed_at` ⚠ | 40 | 37 | 36 | 36 | 38 | 61 | 34 | 29 | 30 |
| `payload.issue.comments` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.comments_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.created_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary.blocked_by` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary.blocking` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary.total_blocked_by` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary.total_blocking` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.issue_field_values` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 |
| `payload.issue.labels` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.labels_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.locked` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.milestone` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.closed_at` | <1 | <1 | <1 | <1 | <1 | <1 | 0 | <1 | 0 |
| `payload.issue.milestone.closed_issues` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.created_at` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.creator` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.description` | 18 | 11 | 9 | 6 | 6 | 4 | 6 | 13 | 19 |
| `payload.issue.milestone.due_on` | 7 | 5 | 4 | 3 | 4 | 3 | 2 | 6 | <1 |
| `payload.issue.milestone.html_url` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.id` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.labels_url` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.node_id` | 0 | 0 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.number` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.open_issues` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.state` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.title` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.updated_at` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.milestone.url` | 20 | 14 | 10 | 7 | 7 | 4 | 6 | 14 | 21 |
| `payload.issue.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.number` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.parent_issue_url` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 5 | 11 |
| `payload.issue.performed_via_github_app` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.client_id` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.created_at` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.description` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.events` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.external_url` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.html_url` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.id` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.name` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.node_id` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.owner` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.permissions` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.slug` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.performed_via_github_app.updated_at` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 10 |
| `payload.issue.reactions` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.+1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.-1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.confused` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.eyes` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.heart` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.hooray` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.laugh` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.rocket` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.total_count` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.url` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.repository_url` | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.state` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.state_reason` ⚠ | 0 | 0 | 0 | 0 | 40 | 62 | 36 | 30 | 31 |
| `payload.issue.sub_issues_summary` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.sub_issues_summary.completed` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.sub_issues_summary.percent_completed` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.sub_issues_summary.total` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue.timeline_url` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.title` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.type` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.color` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.created_at` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.description` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.id` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.is_enabled` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.name` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.type.updated_at` | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 12 | 2 |
| `payload.issue.updated_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.avatar_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.followers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.following_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.gists_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.gravatar_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.login` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.organizations_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.received_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.repos_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.site_admin` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.starred_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.subscriptions_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.label` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.color` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.default` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.description` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 25 | 33 |
| `payload.label.id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.name` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.label.url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | 39 |
| `payload.labels` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 34 | 39 |

## IssueCommentEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 2,158 | 3,927 | 4,768 | 8,681 | 7,885 | 11,213 | 6,581 | 3,791 | 926 |
| `payload.action` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.author_association` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.comment.body` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.created_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.issue_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.performed_via_github_app` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.client_id` | 0 | 0 | 0 | 0 | 0 | 0 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.created_at` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.description` | 0 | 0 | 0 | 0 | <1 | 42 | 49 | 49 | 63 |
| `payload.comment.performed_via_github_app.events` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.external_url` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.html_url` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.id` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.name` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.node_id` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.owner` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.permissions` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.slug` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.performed_via_github_app.updated_at` | 0 | 0 | 0 | 0 | <1 | 42 | 50 | 50 | 63 |
| `payload.comment.reactions` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.+1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.-1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.confused` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.eyes` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.heart` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.hooray` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.laugh` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.rocket` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.total_count` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.reactions.url` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.updated_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.avatar_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.followers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.following_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.gists_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.gravatar_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.login` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.organizations_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.received_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.repos_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.site_admin` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.starred_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.subscriptions_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.comment.user.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.issue` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.active_lock_reason` | 0 | 0 | 0 | 0 | 0 | <1 | <1 | <1 | 0 |
| `payload.issue.assignee` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.avatar_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.events_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.followers_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.following_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.gists_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.gravatar_id` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.html_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.id` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.login` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.node_id` | 0 | 0 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.organizations_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.received_events_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.repos_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.site_admin` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.starred_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.subscriptions_url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.type` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.url` | 14 | 18 | 14 | 14 | 12 | 16 | 16 | 15 | 9 |
| `payload.issue.assignee.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 15 | 9 |
| `payload.issue.assignees` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.author_association` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.issue.body` | 100 | 99 | 98 | 99 | 94 | 91 | 89 | 88 | 98 |
| `payload.issue.closed_at` | 21 | 21 | 21 | 16 | 14 | 26 | 20 | 35 | 30 |
| `payload.issue.comments` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.comments_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.created_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.draft` | 0 | 0 | 0 | 0 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.issue_dependencies_summary` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.issue_dependencies_summary.blocked_by` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.issue_dependencies_summary.blocking` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.issue_dependencies_summary.total_blocked_by` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.issue_dependencies_summary.total_blocking` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.issue_field_values` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 36 |
| `payload.issue.labels` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.labels_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.locked` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.milestone` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.closed_at` | <1 | <1 | <1 | <1 | <1 | <1 | <1 | <1 | 0 |
| `payload.issue.milestone.closed_issues` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.created_at` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.creator` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.description` | 12 | 10 | 6 | 5 | 2 | 3 | 3 | 2 | 2 |
| `payload.issue.milestone.due_on` | 6 | 6 | 3 | 2 | 1 | 1 | 1 | 1 | <1 |
| `payload.issue.milestone.html_url` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.id` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.labels_url` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.node_id` | 0 | 0 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.number` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.open_issues` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.state` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.title` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.updated_at` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.milestone.url` | 14 | 12 | 8 | 5 | 3 | 3 | 3 | 3 | 3 |
| `payload.issue.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.number` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.parent_issue_url` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 2 |
| `payload.issue.performed_via_github_app` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.client_id` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.created_at` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.description` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.events` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.external_url` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.html_url` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.id` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.name` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.node_id` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.owner` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.permissions` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.slug` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.performed_via_github_app.updated_at` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | <1 | 19 |
| `payload.issue.pull_request` | 35 | 42 | 43 | 54 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.pull_request.diff_url` | 35 | 42 | 43 | 54 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.pull_request.html_url` | 35 | 42 | 43 | 54 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.pull_request.merged_at` | 0 | 0 | 0 | 0 | 5 | 5 | 5 | 12 | 12 |
| `payload.issue.pull_request.patch_url` | 35 | 42 | 43 | 54 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.pull_request.url` | 35 | 42 | 43 | 54 | 71 | 66 | 72 | 71 | 65 |
| `payload.issue.reactions` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.+1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.-1` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.confused` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.eyes` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.heart` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.hooray` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.laugh` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.rocket` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.total_count` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.reactions.url` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.repository_url` | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.state` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.state_reason` | 0 | 0 | 0 | 0 | 7 | 10 | 9 | 9 | 10 |
| `payload.issue.sub_issues_summary` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.sub_issues_summary.completed` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.sub_issues_summary.percent_completed` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.sub_issues_summary.total` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 29 | 35 |
| `payload.issue.timeline_url` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.title` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.type` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.color` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.created_at` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.description` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.id` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.is_enabled` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.name` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.type.updated_at` | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 2 | <1 |
| `payload.issue.updated_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.avatar_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.followers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.following_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.gists_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.gravatar_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.login` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.organizations_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.received_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.repos_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.site_admin` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.starred_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.subscriptions_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.issue.user.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |

## PullRequestEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 1,118 | 2,733 | 3,868 | 12,003 | 40,702 | 17,884 | 14,797 | 8,222 | 1,649 |
| `payload.action` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.assignee` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.avatar_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.events_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.followers_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.following_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.gists_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.gravatar_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.html_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.login` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.organizations_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.received_events_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.repos_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.site_admin` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.starred_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.subscriptions_url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.type` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignee.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.assignees` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 2 |
| `payload.label` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.color` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.default` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.description` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 36 | 14 |
| `payload.label.id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.name` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.node_id` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.label.url` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 47 | 18 |
| `payload.labels` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 48 | 18 |
| `payload.number` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request._links` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.comments` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.commits` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.html` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.issue` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.review_comment` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.review_comments` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.self` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.statuses` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.additions` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.assignee` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.avatar_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.events_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.followers_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.following_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.gists_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.gravatar_id` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.html_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.id` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.login` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.node_id` | 0 | 0 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.organizations_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.received_events_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.repos_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.site_admin` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.starred_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.subscriptions_url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.type` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.url` | 2 | 7 | 6 | 4 | 1 | 7 | 5 | 0 | 0 |
| `payload.pull_request.assignee.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 |
| `payload.pull_request.assignees` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.author_association` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.auto_merge` | 0 | 0 | 0 | 0 | <1 | 2 | 1 | 0 | 0 |
| `payload.pull_request.auto_merge.commit_message` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.auto_merge.commit_title` | 0 | 0 | 0 | 0 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.auto_merge.enabled_by` | 0 | 0 | 0 | 0 | <1 | 2 | 1 | 0 | 0 |
| `payload.pull_request.auto_merge.merge_method` | 0 | 0 | 0 | 0 | <1 | 2 | 1 | 0 | 0 |
| `payload.pull_request.base` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.label` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.base.ref` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.repo` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.sha` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.user` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.body` ⚠ | 98 | 95 | 97 | 99 | 93 | 72 | 82 | 0 | 0 |
| `payload.pull_request.changed_files` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.closed_at` | 47 | 49 | 47 | 45 | 14 | 49 | 38 | 0 | 0 |
| `payload.pull_request.comments` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.comments_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.commits` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.commits_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.created_at` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.deletions` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.diff_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.draft` ⚠ | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.head` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.label` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.head.ref` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.repo` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.sha` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.user` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.html_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.issue_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.labels` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.locked` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.maintainer_can_modify` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.merge_commit_sha` ⚠ | 54 | 56 | 48 | 46 | 14 | 75 | 46 | 0 | 0 |
| `payload.pull_request.mergeable` | 16 | 14 | 7 | 13 | 5 | 36 | 19 | 0 | 0 |
| `payload.pull_request.mergeable_state` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.merged` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.merged_at` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.avatar_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.events_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.followers_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.following_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.gists_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.gravatar_id` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.html_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.id` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.login` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.node_id` | 0 | 0 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.organizations_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.received_events_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.repos_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.site_admin` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.starred_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.subscriptions_url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.type` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.url` | 40 | 42 | 40 | 32 | 8 | 37 | 28 | 0 | 0 |
| `payload.pull_request.merged_by.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 | 0 |
| `payload.pull_request.milestone` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.closed_at` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | 0 | 0 |
| `payload.pull_request.milestone.closed_issues` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.created_at` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.creator` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.description` | <1 | 2 | 2 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.due_on` | <1 | 1 | <1 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.html_url` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.id` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.labels_url` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.node_id` | 0 | 0 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.number` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.open_issues` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.state` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.title` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.updated_at` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.milestone.url` | <1 | 3 | 3 | <1 | <1 | <1 | <1 | 0 | 0 |
| `payload.pull_request.node_id` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.number` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.patch_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.rebaseable` | 0 | 0 | 7 | 13 | 5 | 36 | 19 | 0 | 0 |
| `payload.pull_request.requested_reviewers` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.requested_teams` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.review_comment_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.review_comments` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.review_comments_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.state` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.statuses_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.title` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.updated_at` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.user` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.avatar_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.events_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.followers_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.following_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.gists_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.gravatar_id` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.html_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.id` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.login` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.node_id` ⚠ | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.organizations_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.received_events_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.repos_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.site_admin` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.starred_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.subscriptions_url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.type` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.url` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.user_view_type` ⚠ | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 0 | 0 |

## PullRequestReviewEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 0 | 0 | 0 | 0 | 3,487 | 6,500 | 3,924 | 2,359 | 351 |
| `payload.action` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request._links` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.comments` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.commits` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.html` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.issue` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.review_comment` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.review_comments` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.self` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request._links.statuses` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.assignee` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.avatar_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.events_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.followers_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.following_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.gists_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.gravatar_id` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.html_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.id` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.login` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.node_id` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.organizations_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.received_events_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.repos_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.site_admin` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.starred_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.subscriptions_url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.type` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.url` | — | — | — | — | 17 | 20 | 21 | 0 | 0 |
| `payload.pull_request.assignee.user_view_type` | — | — | — | — | 0 | 0 | 21 | 0 | 0 |
| `payload.pull_request.assignees` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.author_association` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.auto_merge` | — | — | — | — | 2 | 3 | 3 | 0 | 0 |
| `payload.pull_request.auto_merge.commit_message` | — | — | — | — | <1 | 1 | 1 | 0 | 0 |
| `payload.pull_request.auto_merge.commit_title` | — | — | — | — | <1 | 1 | 1 | 0 | 0 |
| `payload.pull_request.auto_merge.enabled_by` | — | — | — | — | 2 | 3 | 3 | 0 | 0 |
| `payload.pull_request.auto_merge.merge_method` | — | — | — | — | 2 | 3 | 3 | 0 | 0 |
| `payload.pull_request.base` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.label` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.base.ref` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.repo` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.sha` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.base.user` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.body` ⚠ | — | — | — | — | 80 | 82 | 84 | 0 | 0 |
| `payload.pull_request.closed_at` | — | — | — | — | 2 | 2 | 3 | 0 | 0 |
| `payload.pull_request.comments_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.commits_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.created_at` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.diff_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.draft` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.head` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.label` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.head.ref` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.repo` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.sha` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.head.user` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.html_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.issue_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.labels` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.locked` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.merge_commit_sha` ⚠ | — | — | — | — | 99 | 99 | 95 | 0 | 0 |
| `payload.pull_request.merged_at` | — | — | — | — | 2 | 2 | 3 | 0 | 0 |
| `payload.pull_request.milestone` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.closed_at` | — | — | — | — | 0 | 0 | <1 | 0 | 0 |
| `payload.pull_request.milestone.closed_issues` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.created_at` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.creator` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.description` | — | — | — | — | 3 | 3 | 3 | 0 | 0 |
| `payload.pull_request.milestone.due_on` | — | — | — | — | 1 | 1 | 1 | 0 | 0 |
| `payload.pull_request.milestone.html_url` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.id` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.labels_url` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.node_id` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.number` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.open_issues` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.state` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.title` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.updated_at` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.milestone.url` | — | — | — | — | 4 | 4 | 3 | 0 | 0 |
| `payload.pull_request.node_id` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.number` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.patch_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.requested_reviewers` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.requested_teams` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.review_comment_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.review_comments_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.state` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.statuses_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.title` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.updated_at` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.pull_request.user` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.avatar_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.events_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.followers_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.following_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.gists_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.gravatar_id` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.html_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.id` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.login` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.node_id` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.organizations_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.received_events_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.repos_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.site_admin` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.starred_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.subscriptions_url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.type` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.url` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.pull_request.user.user_view_type` ⚠ | — | — | — | — | 0 | 0 | 100 | 0 | 0 |
| `payload.review` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review._links` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review._links.html` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review._links.pull_request` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.author_association` ⚠ | — | — | — | — | 100 | 100 | 100 | 0 | 0 |
| `payload.review.body` | — | — | — | — | 60 | 67 | 38 | 41 | 55 |
| `payload.review.commit_id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.html_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.node_id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.pull_request_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.state` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.submitted_at` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.updated_at` | — | — | — | — | 0 | 0 | 100 | 100 | 100 |
| `payload.review.user` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.avatar_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.events_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.followers_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.following_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.gists_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.gravatar_id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.html_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.login` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.node_id` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.organizations_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.received_events_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.repos_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.site_admin` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.starred_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.subscriptions_url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.type` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.url` | — | — | — | — | 100 | 100 | 100 | 100 | 100 |
| `payload.review.user.user_view_type` | — | — | — | — | 0 | 0 | 100 | 100 | 100 |

## ReleaseEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 96 | 164 | 238 | 450 | 572 | 1,277 | 800 | 450 | 324 |
| `payload.action` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.assets` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.assets_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.avatar_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.followers_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.following_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.gists_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.gravatar_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.login` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.organizations_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.received_events_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.repos_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.site_admin` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.starred_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.subscriptions_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.author.user_view_type` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.release.body` | 95 | 94 | 95 | 97 | 98 | 94 | 95 | 98 | 96 |
| `payload.release.created_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.discussion_url` | 0 | 0 | 0 | 0 | <1 | <1 | 0 | <1 | 0 |
| `payload.release.draft` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.html_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.immutable` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.release.is_short_description_html_truncated` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.mentions` | 0 | 0 | 0 | 0 | 10 | 11 | 12 | 12 | 2 |
| `payload.release.mentions_count` | 0 | 0 | 0 | 0 | 10 | 11 | 12 | 12 | 2 |
| `payload.release.name` | 95 | 95 | 95 | 99 | 98 | 97 | 97 | 99 | 99 |
| `payload.release.node_id` | 0 | 0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.prerelease` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.published_at` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.reactions` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.+1` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.-1` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.confused` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.eyes` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.heart` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.hooray` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.laugh` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.rocket` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.total_count` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.reactions.url` | 0 | 0 | 0 | 0 | 0 | 0 | <1 | <1 | 0 |
| `payload.release.short_description_html` | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.tag_name` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.tarball_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.target_commitish` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.updated_at` | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 |
| `payload.release.upload_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.release.zipball_url` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

## CreateEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 2,518 | 5,991 | 8,443 | 19,120 | 45,066 | 38,096 | 21,704 | 13,499 | 3,732 |
| `payload.description` | 97 | 89 | 51 | 52 | 43 | 33 | 50 | 45 | 58 |
| `payload.full_ref` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 |
| `payload.master_branch` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.pusher_type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.ref` | 61 | 65 | 68 | 71 | 90 | 78 | 74 | 100 | 100 |
| `payload.ref_type` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

## PublicEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 26 | 17 | 72 | 359 | 356 | 760 | 484 | 81 | 8 |

## PushEvent

| path | 2015-03-02 | 2016-06-01 | 2018-06-01 | 2020-06-01 | 2022-06-01 | 2024-06-03 | 2025-09-01 | 2025-11-03 | 2026-10-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| *(rows in sample)* | 12,449 | 23,396 | 35,241 | 58,390 | 59,270 | 168,238 | 101,718 | 117,207 | 30,564 |
| `payload.before` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.commits` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.distinct_size` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
| `payload.head` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.push_id` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.ref` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| `payload.repository_id` | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 100 | 100 |
| `payload.size` ⚠ | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 |
