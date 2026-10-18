-- depends_on: {{ source('lake_push', 'push_daily') }}
select
    p.repo_id,
    p.actor_id,
    p.day,
    p.n_pushes
from {{ lake_events('push_daily') }} as p
anti join {{ ref('stg_bot_actors') }} as b on b.actor_id = p.actor_id
where p.day >= date '{{ var("events_start") }}' and p.day < date '{{ var("events_end") }}'
