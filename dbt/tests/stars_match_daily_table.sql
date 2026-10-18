-- n_stars in int_repo_daily_activity must equal int_repo_star_daily for the young-moving repos
select a.repo_id, a.day, a.n_stars as activity_stars, s.n_stars as daily_stars
from {{ ref('int_repo_daily_activity') }} a
full outer join (
    select d.* from {{ ref('int_repo_star_daily') }} d
    semi join {{ ref('int_young_moving_repos') }} using (repo_id)
) s using (repo_id, day)
where coalesce(a.n_stars, 0) <> coalesce(s.n_stars, 0)
