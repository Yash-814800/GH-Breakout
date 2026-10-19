-- labels exist only for matured snapshot dates, and every matured candidate has a label
select l.repo_id, l.snapshot_date
from {{ ref('mart_labels') }} l
join {{ ref('mart_snapshot_dates') }} s using (snapshot_date)
where not s.is_label_matured
union all
select c.repo_id, c.snapshot_date
from {{ ref('mart_candidates') }} c
join {{ ref('mart_snapshot_dates') }} s using (snapshot_date)
left join {{ ref('mart_labels') }} l using (repo_id, snapshot_date)
where s.is_label_matured and l.repo_id is null
