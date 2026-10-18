{{ config(materialized='table') }}

{#
  Automation accounts. Three rules, none of which looks at star activity:
    1. login ends in [bot], -bot or _bot (case-insensitive)
    2. login is in the known_bots seed
    3. extreme non-star activity: > 1,000 events on one UTC day, on >= 3 distinct days
       (all kept event types except WatchEvent, plus pushes from push_daily)
  Evidence comes from stg_bot_actor_signals (built month by month, ADR-020), restricted to the
  months of the events window.
#}

with s as (
    select * from {{ ref('stg_bot_actor_signals') }}
    where month >= date_trunc('month', date '{{ var("events_start") }}')
      and month < date '{{ var("events_end") }}'
),
by_login as (
    select distinct actor_id, 'login_pattern' as reason
    from s
    where regexp_matches(bot_like_login, '(\[bot\]|[-_]bot)$', 'i')
),
by_seed as (
    select distinct s.actor_id, 'known_bots_seed' as reason
    from s
    join {{ ref('known_bots') }} k on lower(s.bot_like_login) = lower(k.login)
),
by_volume as (
    select actor_id, 'extreme_non_star_activity' as reason
    from s
    group by actor_id
    having sum(n_busy_days) >= 3
)
select actor_id, min(reason) as reason
from (
    select * from by_login union all select * from by_seed union all select * from by_volume
)
group by actor_id
