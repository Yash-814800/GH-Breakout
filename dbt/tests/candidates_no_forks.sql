-- no candidate may be a fork or mirror-like repo
select c.repo_id, c.snapshot_date
from {{ ref('mart_candidates') }} c
join {{ ref('int_repo_birth') }} b using (repo_id)
where b.is_mirror_like {% if var('exclude_forks') %}or b.is_fork{% endif %}
