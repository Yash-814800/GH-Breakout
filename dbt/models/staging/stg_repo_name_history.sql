-- depends_on: {{ source('enrich', 'repo_name_history') }}
{# display-only: never join events on repo_name #}
select repo_id, repo_name, first_seen, last_seen, n_events
from {{ source('enrich', 'repo_name_history') }}
