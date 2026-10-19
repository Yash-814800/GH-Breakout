{#
  'Top q' tastemaker score per month boundary M (first of month). Among actors with early_stars_known >=
  tm_min_known as of M (outcome_day < M), the smallest smoothed score that still belongs to the top
  tm_top_quantile. Grain month. Ties at the threshold stay in the group.

  An actor's (early_stars_known, hits_known) state is stored once per outcome_day, so the number of actors
  per state at M is a running sum of +1 (state starts, day outcome_day + 1) and -1 (next state starts,
  day next_outcome_day + 1), no per-month scan of the actor table. Score = (h + alpha) / (n + alpha + beta).
#}
with ev as (
    select early_stars_known as n, hits_known as h, outcome_day + 1 as d, 1 as delta
    from {{ ref('int_actor_early_cum') }} where early_stars_known >= {{ var('tm_min_known') }}
    union all
    select early_stars_known, hits_known, next_outcome_day + 1, -1
    from {{ ref('int_actor_early_cum') }}
    where early_stars_known >= {{ var('tm_min_known') }} and next_outcome_day is not null
),
d as (select n, h, d, sum(delta) as dl from ev group by 1, 2, 3),
cumd as (select n, h, d, sum(dl) over (partition by n, h order by d) as c from d),
bounds as (
    select date_trunc('month', min(d))::date as m0,
           {% if var('snapshot_dates_mode') == 'single' %}
           greatest(date_trunc('month', max(d))::date, date_trunc('month', date '{{ var("snapshot_date") }}')::date) as m1
           {% else %}
           date_trunc('month', max(d))::date as m1
           {% endif %}
    from d
),
months as (select m::date as month from bounds, generate_series(m0, m1, interval 1 month) t(m)),
states as (
    select m.month, c.n, c.h, c.c
    from months m
    cross join (select distinct n, h from d) k
    asof left join cumd c on c.n = k.n and c.h = k.h and m.month >= c.d
    where c.c > 0
),
scored as (
    select month, (h + {{ var('tm_alpha') }}) / (n + {{ var('tm_alpha') }} + {{ var('tm_beta') }}) as score, sum(c) as actors
    from states
    group by 1, 2
),
ranked as (
    select month, score, actors,
           sum(actors) over (partition by month order by score) as cum_actors,
           sum(actors) over (partition by month) as total_actors
    from scored
)
select month,
       min(score) filter (where cum_actors >= (1 - {{ var('tm_top_quantile') }}) * total_actors) as score_threshold,
       max(total_actors)::bigint as n_actors
from ranked
group by 1
