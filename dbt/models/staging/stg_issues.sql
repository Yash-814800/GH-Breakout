-- depends_on: {{ source('lake', 'IssuesEvent') }}
{# one row per event_id (lake guarantees uniqueness, see lake_files); bots excluded #}
select
    e.event_id,
    e.created_at,
    e.repo_id,
    e.repo_name,
    e.actor_id,
    e.actor_login,
    e.detail_level,
    e.action,
    e.number,
    e.target_user_id,
    e.target_created_at
from {{ lake_events('IssuesEvent') }} as e
anti join {{ ref('stg_bot_actors') }} as b on b.actor_id = e.actor_id
where {{ window_filter('e.created_at') }}
