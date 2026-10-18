-- depends_on: {{ source('enrich', 'repo_metadata') }}
{# status 'not_found' = unresolvable now (deleted/private/blocked): metadata is UNKNOWN, not false #}
select
    repo_id,
    status,
    fetched_at,
    created_at as api_created_at,
    is_fork,
    parent_repo_id,
    is_archived,
    is_mirror,
    is_template,
    primary_language,
    owner_type,
    owner_id,
    owner_created_at
from {{ source('enrich', 'repo_metadata') }}
