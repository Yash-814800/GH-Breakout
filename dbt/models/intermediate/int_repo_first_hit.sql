{#
  Grain repo_id: the day after which a repo is known to have been a 'hit' under the tastemaker rule
  (an early star followed by >= absolute_min_gain stars within tm_lookahead_days). A consumer at
  snapshot D may use it only when first_hit_outcome_day < D. Used by feat_owner.
#}
select repo_id, min(outcome_day) as first_hit_outcome_day
from {{ ref('int_actor_early_stars') }}
where is_hit
group by 1
