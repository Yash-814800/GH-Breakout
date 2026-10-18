-- depends_on: {{ source('enrich', 'trending') }}
{# language_filter IS NULL = all-languages list (the series for the lead-time metric) #}
select date as trending_date, rank, repo_id, repo_name, language_filter, source
from {{ source('enrich', 'trending') }}
