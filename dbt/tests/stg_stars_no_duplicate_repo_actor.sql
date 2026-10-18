-- stg_stars keeps the first star per (repo_id, actor_id): no duplicates (checked on a repo sample)
select repo_id, actor_id, count(*) as n
from {{ ref('stg_stars') }}
where repo_id % 53 = 0
group by 1, 2
having count(*) > 1
