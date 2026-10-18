{#
  Grain repo_id: repos that on some day d were young (d - birth_day <= max_age_days) and had
  >= min_stars_14d stars in [d-14, d). Superset of all candidates (forks/mirrors are NOT removed
  here, Phase 6 does that). Every expensive model downstream is restricted to these repos.
  The earliest qualifying d is always (a star day) + 1, so only star days are examined.
  Left-censored repos (first event near events_start, no API date) are excluded.
#}
with d as (
    select s.repo_id, s.day, s.n_stars, b.birth_at::date as birth_day
    from {{ ref('int_repo_star_daily') }} s
    join {{ ref('int_repo_birth') }} b using (repo_id)
    where not b.is_left_censored
),
w as (
    select repo_id, day, birth_day,
        sum(n_stars) over (
            partition by repo_id order by day
            range between interval 13 days preceding and current row
        ) as stars_14d
    from d
)
select repo_id, min(day) + 1 as first_moving_day
from w
where stars_14d >= {{ var('min_stars_14d') }}
  and (day + 1) - birth_day between 0 and {{ var('max_age_days') }}
group by 1
