-- depends_on: {{ source('enrich', 'actor_id_age_map') }}
select actor_id_breakpoint, est_created_at
from {{ source('enrich', 'actor_id_age_map') }}
