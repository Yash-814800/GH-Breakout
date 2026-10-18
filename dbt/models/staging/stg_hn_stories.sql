-- depends_on: {{ source('enrich', 'hn_stories') }}
{# points/num_comments are fetch-time values (ADR-019): features may use them only for D - 3 days #}
select story_id, created_at, points, num_comments, repo_id, repo_name, fetched_at
from {{ source('enrich', 'hn_stories') }}
