{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Per actor, running counts of early stars whose outcome is known, ordered by outcome_day. A row holds
  from snapshot outcome_day + 1 until next_outcome_day (inclusive): consumers ASOF-join with
  `D > outcome_day`, which is strictly "outcome known before D". Grain (actor_id, outcome_day).
  Built per actor_id hash bucket (ADR-020).
#}
with a as (
    select actor_id, outcome_day, count(*)::integer as n, sum(is_hit::integer)::integer as h
    from {{ ref('int_actor_early_stars') }}
    where {{ bucket_filter('actor_id') }}
    group by 1, 2
)
select
    {{ bucket_col('actor_id') }} as bucket, actor_id, outcome_day,
    (sum(n) over w)::integer as early_stars_known,
    (sum(h) over w)::integer as hits_known,
    lead(outcome_day) over (partition by actor_id order by outcome_day) as next_outcome_day
from a
window w as (partition by actor_id order by outcome_day rows between unbounded preceding and current row)
