{#
  Tier B features are NULL (never 0) where the window has no detail coverage, and detail_coverage_28d is 0 there.
#}
select repo_id, snapshot_date
from {{ ref('feat_detail') }}
where snapshot_date <= date '{{ var("detail_start_date") }}'
  and (issues_opened_28d is not null or prs_opened_28d is not null or tags_created_total_before is not null
       or median_first_response_hours_28d is not null or core_actor_count_90d is not null
       or detail_coverage_28d <> 0)
