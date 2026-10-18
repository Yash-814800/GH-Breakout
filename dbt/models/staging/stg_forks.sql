-- depends_on: {{ source('lake', 'ForkEvent') }}
{# one row per event_id (lake guarantees uniqueness, see lake_files); bots excluded #}
select
    e.event_id,
    e.created_at,
    e.repo_id,
    e.repo_name,
    e.actor_id,
    e.actor_login,
    e.detail_level,
    e.forkee_repo_id
from {{ lake_events('ForkEvent') }} as e
anti join {{ ref('stg_bot_actors') }} as b on b.actor_id = e.actor_id
where {{ window_filter('e.created_at') }}
