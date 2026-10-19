{#
  mart_repo_features has exactly one row per candidate (a left join must never drop or duplicate candidates).
#}
select 'missing' as problem, count(*) as n
from {{ ref('mart_candidates') }} c
anti join {{ ref('mart_repo_features') }} f using (repo_id, snapshot_date)
having count(*) > 0
union all
select 'extra', count(*)
from {{ ref('mart_repo_features') }} f
anti join {{ ref('mart_candidates') }} c using (repo_id, snapshot_date)
having count(*) > 0
