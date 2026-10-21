{{ config(materialized='view') }}
{#
  Grain (repo_id, similar_repo_id). Co-star similarity (Phase 11, §11.2).
  Cosine = overlap / sqrt(n_a * n_b) for candidate repositories.
  Requires overlap >= 5; cosine strictly in (0, 1].
#}
with cand as (
    select distinct repo_id from {{ ref('mart_candidates') }}
),
cand_stars as (
    select s.repo_id, s.actor_id
    from {{ ref('stg_stars') }} s
    join cand c on s.repo_id = c.repo_id
    where s.actor_id not in (select actor_id from {{ ref('stg_bot_actors') }})
    group by 1, 2
),
cand_sizes as (
    select repo_id, count(distinct actor_id) as n_a
    from cand_stars
    group by 1
),
co_stars as (
    select c1.repo_id, c2.repo_id as similar_repo_id,
           count(distinct c1.actor_id) as overlap
    from cand_stars c1
    join cand_stars c2 on c1.actor_id = c2.actor_id and c1.repo_id != c2.repo_id
    group by 1, 2
    having count(distinct c1.actor_id) >= 5
),
sim_sizes as (
    select repo_id as similar_repo_id, n_a as n_b
    from cand_sizes
),
ranked as (
    select cs.repo_id, cs.similar_repo_id, cs.overlap,
           round(cs.overlap::double / sqrt(ca.n_a::double * cb.n_b::double), 4) as cosine,
           row_number() over (
               partition by cs.repo_id
               order by cs.overlap::double / sqrt(ca.n_a::double * cb.n_b::double) desc, cs.overlap desc
           ) as rank
    from co_stars cs
    join cand_sizes ca on cs.repo_id = ca.repo_id
    join sim_sizes cb on cs.similar_repo_id = cb.similar_repo_id
),
latest_names as (
    select repo_id, repo_name,
           row_number() over (partition by repo_id order by first_seen desc) as rn
    from {{ ref('stg_repo_name_history') }}
)
select
    r.repo_id,
    r.similar_repo_id,
    r.overlap,
    r.cosine,
    coalesce(ln.repo_name, 'repo_id=' || r.similar_repo_id) as similar_repo_name,
    m.primary_language as similar_language
from ranked r
left join {{ ref('stg_repo_metadata') }} m on m.repo_id = r.similar_repo_id
left join latest_names ln on ln.repo_id = r.similar_repo_id and ln.rn = 1
where r.rank <= 5
  and r.cosine > 0.0
  and r.cosine <= 1.0
  and coalesce(m.parent_repo_id, 0) != r.repo_id
