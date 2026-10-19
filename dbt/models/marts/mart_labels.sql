{#
  Grain (repo_id, snapshot_date): outcomes of the candidates on MATURED snapshot dates only.
    gain_30d          first stars in [D, D + horizon_days)
    threshold_rel     GREATEST(relative_floor_gain, quantile_cont(gain_30d, relative_quantile)) over ALL
                      candidates on D (a property of the label definition, never train- or test-only)
    breakout_rel      gain_30d >= threshold_rel   (primary, about the top 0.5%)
    breakout_abs      gain_30d >= absolute_min_gain (secondary)
    days_to_threshold first day offset in [0, horizon) at which the forward cumulative stars reach
                      threshold_rel (NULL if never)
    first_trending_date  first date in [D, D + 60) on an all-languages Trending list (NULL if never)
    trending_covered  >= 54 of the 60 days of that window have an all-languages Trending list; when
                      FALSE, first_trending_date NULL means "unknown", not "never trended"
  Labels read stars after D by design; they are never features.
#}
with cands as (
    select c.repo_id, c.snapshot_date
    from {{ ref('mart_candidates') }} c
    join {{ ref('mart_snapshot_dates') }} s using (snapshot_date)
    where s.is_label_matured
),
daily as (
    select repo_id, day, n_stars from {{ ref('int_repo_star_daily') }}
    where repo_id in (select repo_id from cands)
),
fwd as (
    select c.repo_id, c.snapshot_date, d.day, d.n_stars
    from cands c
    join daily d on d.repo_id = c.repo_id
     and d.day >= c.snapshot_date and d.day < c.snapshot_date + {{ var('horizon_days') }}
),
gains as (
    select c.repo_id, c.snapshot_date, coalesce(sum(f.n_stars), 0)::integer as gain_30d
    from cands c
    left join fwd f using (repo_id, snapshot_date)
    group by 1, 2
),
thr as (
    select snapshot_date,
           greatest({{ var('relative_floor_gain') }},
                    quantile_cont(gain_30d, {{ var('relative_quantile') }})) as threshold_rel,
           count(*) as n_candidates
    from gains
    group by 1
),
hit as (
    select repo_id, snapshot_date, min(day - snapshot_date) as days_to_threshold
    from (
        select f.repo_id, f.snapshot_date, f.day,
               sum(f.n_stars) over (partition by f.repo_id, f.snapshot_date order by f.day) as cum
        from fwd f
    ) x
    join thr using (snapshot_date)
    where cum >= threshold_rel
    group by 1, 2
),
trend_days as (
    select s.snapshot_date, count(distinct t.trending_date) as n_days
    from (select distinct snapshot_date from cands) s
    left join (select distinct trending_date from {{ ref('stg_trending') }} where language_filter is null) t
      on t.trending_date >= s.snapshot_date and t.trending_date < s.snapshot_date + 60
    group by 1
),
first_trend as (
    select c.repo_id, c.snapshot_date, min(t.trending_date) as first_trending_date
    from cands c
    join {{ ref('stg_trending') }} t
      on t.repo_id = c.repo_id and t.language_filter is null
     and t.trending_date >= c.snapshot_date and t.trending_date < c.snapshot_date + 60
    group by 1, 2
)
select
    g.repo_id,
    g.snapshot_date,
    g.gain_30d,
    t.threshold_rel,
    g.gain_30d >= t.threshold_rel as breakout_rel,
    g.gain_30d >= {{ var('absolute_min_gain') }} as breakout_abs,
    h.days_to_threshold,
    ft.first_trending_date,
    td.n_days >= 54 as trending_covered
from gains g
join thr t using (snapshot_date)
join trend_days td using (snapshot_date)
left join hit h using (repo_id, snapshot_date)
left join first_trend ft using (repo_id, snapshot_date)
