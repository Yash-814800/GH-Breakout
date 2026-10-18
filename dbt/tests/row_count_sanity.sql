{{ config(severity='warn') }}
-- warn when a model is empty or the intermediate chain collapses unexpectedly
select model, n
from (
    select 'stg_stars' as model, count(*) as n from {{ ref('stg_stars') }}
    union all select 'int_repo_star_daily', count(*) from {{ ref('int_repo_star_daily') }}
    union all select 'int_young_moving_repos', count(*) from {{ ref('int_young_moving_repos') }}
    union all select 'int_repo_daily_activity', count(*) from {{ ref('int_repo_daily_activity') }}
    union all select 'int_star_events_enriched', count(*) from {{ ref('int_star_events_enriched') }}
)
where n = 0
