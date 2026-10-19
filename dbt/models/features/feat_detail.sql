{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier B: needs payload detail (detail_level 1, from detail_start_date). Grain (repo_id, snapshot_date).
  NULL, never 0, where the window has no detail coverage; detail_coverage_28d tells the model how much of
  the 28-day window is covered. A repo-day without a row has no events, so inside a covered window a missing
  sum is 0, not NULL.
  Responses and merges only count when they happened before D: an issue opened in the window whose first
  response comes after D is excluded from the median (and is 'not responded' for the 48 h share, which only
  looks at issues opened before D - 2 days so the 48 h window is fully inside the past).
  PR merged flag / author are NULL in payloads from payload_trim_date (ADR-007): merge features are NULL for
  windows reaching that day. Windows [D - n, D): the last day is D - 1.
#}
with c as (
    select repo_id, snapshot_date, bucket,
        least(28, greatest(0, snapshot_date - date '{{ var("detail_start_date") }}')) as cov_days,
        (snapshot_date - 1) >= date '{{ var("payload_trim_date") }}' as merge_unavailable
    from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
da as (
    select c.repo_id, c.snapshot_date, d.day, d.n_issues_opened, d.n_issues_closed, d.n_prs_opened, d.n_prs_merged,
           d.n_creates_tag
    from c
    join {{ ref('int_repo_daily_activity') }} d
      on d.repo_id = c.repo_id and d.day < c.snapshot_date
    where {{ bucket_filter('d.repo_id') }}
),
daily as (
    select repo_id, snapshot_date,
        sum(n_issues_opened) filter (where day >= snapshot_date - 28) as issues_opened,
        sum(n_issues_closed) filter (where day >= snapshot_date - 28) as issues_closed,
        sum(n_prs_opened) filter (where day >= snapshot_date - 28) as prs_opened,
        sum(n_prs_merged) filter (where day >= snapshot_date - 28) as prs_merged,
        sum(n_creates_tag) as tags_total,
        max(day) as max_day
    from da group by 1, 2
),
iss as (
    select c.repo_id, c.snapshot_date,
        median(date_diff('minute', i.opened_at, i.first_response_at) / 60.0)
            filter (where i.first_response_at < c.snapshot_date) as median_first_response_hours_28d,
        avg(coalesce(i.first_response_at < c.snapshot_date and i.first_response_at <= i.opened_at + interval 48 hour, false)::integer)
            filter (where i.opened_at < c.snapshot_date - 2) as share_issues_responded_48h,
        max(i.opened_at) as max_ts,
        max(i.first_response_at) filter (where i.first_response_at < c.snapshot_date) as max_resp
    from c
    join {{ ref('int_issue_response') }} i
      on i.repo_id = c.repo_id and i.opened_at >= c.snapshot_date - 28 and i.opened_at < c.snapshot_date
    group by 1, 2
),
core as (
    select c.repo_id, c.snapshot_date, k.actor_id, max(k.day) as max_day
    from c
    join {{ ref('int_core_actors_daily') }} k
      on k.repo_id = c.repo_id and k.day >= c.snapshot_date - 90 and k.day < c.snapshot_date
    group by 1, 2, 3
),
core_n as (
    select repo_id, snapshot_date, count(*)::integer as core_actor_count_90d, max(max_day) as max_day
    from core group by 1, 2
),
prm as (
    select c.repo_id, c.snapshot_date,
        median(date_diff('minute', p.opened_at, p.merged_at) / 60.0)
            filter (where p.merged_at >= c.snapshot_date - 28 and p.merged_at < c.snapshot_date) as median_merge_hours_28d,
        max(p.opened_at) as max_ts,
        max(p.merged_at) filter (where p.merged_at < c.snapshot_date) as max_merged
    from c
    join {{ ref('int_pr_lifecycle') }} p
      on p.repo_id = c.repo_id and p.opened_at >= c.snapshot_date - 90 and p.opened_at < c.snapshot_date
    group by 1, 2
),
ext as (
    select c.repo_id, c.snapshot_date, count(distinct p.author_id)::integer as external_pr_authors_28d
    from c
    join {{ ref('int_pr_lifecycle') }} p
      on p.repo_id = c.repo_id and p.opened_at >= c.snapshot_date - 28 and p.opened_at < c.snapshot_date
    anti join core x on x.repo_id = c.repo_id and x.snapshot_date = c.snapshot_date and x.actor_id = p.author_id
    group by 1, 2
),
pr as (
    select m.repo_id, m.snapshot_date, e.external_pr_authors_28d, m.median_merge_hours_28d, m.max_ts, m.max_merged
    from prm m left join ext e using (repo_id, snapshot_date)
)
select
    c.bucket, c.repo_id, c.snapshot_date,
    c.cov_days / 28.0 as detail_coverage_28d,
    case when c.cov_days > 0 then coalesce(d.issues_opened, 0) end as issues_opened_28d,
    case when c.cov_days > 0 then coalesce(d.issues_closed, 0) end as issues_closed_28d,
    case when c.cov_days > 0 then coalesce(d.issues_closed, 0)::double / nullif(d.issues_opened, 0) end as issue_close_ratio_28d,
    case when c.cov_days > 0 then i.median_first_response_hours_28d end as median_first_response_hours_28d,
    case when c.cov_days > 0 then i.share_issues_responded_48h end as share_issues_responded_48h,
    case when c.cov_days > 0 then coalesce(d.prs_opened, 0) end as prs_opened_28d,
    case when c.cov_days > 0 and not c.merge_unavailable then coalesce(d.prs_merged, 0) end as prs_merged_28d,
    case when c.cov_days > 0 and not c.merge_unavailable then p.median_merge_hours_28d end as median_merge_hours_28d,
    case when c.snapshot_date > date '{{ var("detail_start_date") }}' then coalesce(cn.core_actor_count_90d, 0) end as core_actor_count_90d,
    case when c.cov_days > 0 then coalesce(p.external_pr_authors_28d, 0) end as external_pr_authors_28d,
    case when c.cov_days > 0 then coalesce(d.tags_total, 0) end as tags_created_total_before,
    (c.snapshot_date >= date '{{ var("payload_trim_date") }}')::integer as era_post_2025_10,
    greatest(d.max_day::timestamp, i.max_ts, i.max_resp, cn.max_day::timestamp, p.max_ts, p.max_merged) as _max_input_ts
from c
left join daily d using (repo_id, snapshot_date)
left join iss i using (repo_id, snapshot_date)
left join core_n cn using (repo_id, snapshot_date)
left join pr p using (repo_id, snapshot_date)
