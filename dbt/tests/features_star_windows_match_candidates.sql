{#
  feat_star_dynamics recomputes the star windows from the daily table; they must equal the ones the candidate
  definition used (mart_candidates). Returns mismatching rows.
#}
select f.repo_id, f.snapshot_date
from {{ ref('feat_star_dynamics') }} f
join {{ ref('mart_candidates') }} c using (repo_id, snapshot_date)
where f.stars_1d <> c.stars_1d or f.stars_7d <> c.stars_7d or f.stars_14d <> c.stars_14d
   or f.stars_total_before <> c.stars_total_before
   or f.age_days <> c.age_days
   or f.star_accel_7d <> c.stars_7d - c.stars_prev_7d
