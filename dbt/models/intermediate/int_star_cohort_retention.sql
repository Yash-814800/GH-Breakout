{#
  Grain (repo_id, cohort_week): weekly cohorts of early stargazers of young-moving repos, with
  the share who later forked / opened an issue / opened a PR / commented on the same repo within 30,
  60 and 90 days of their star, and the share with any of these. Ratios are only meaningful when
  the horizon has elapsed: is_mature_Nd = (cohort week end + N days <= events_end).
#}
with c as (
    select repo_id, date_trunc('week', starred_at)::date as cohort_week, count(*)::integer as n_stargazers
    from {{ ref('int_early_stars') }}
    group by 1, 2
),
first_action as (
    -- per stargazer and action type: days to the first later action
    select repo_id, actor_id, date_trunc('week', starred_at)::date as cohort_week, action_type,
           min(days_after_star) as d
    from {{ ref('int_stargazer_later_actions') }}
    group by 1, 2, 3, 4
),
agg as (
    select repo_id, cohort_week,
        {% for t in ['fork', 'issue', 'pull_request', 'comment'] %}
        {% for n in [30, 60, 90] %}
        count(*) filter (where action_type = '{{ t }}' and d <= {{ n }}) as n_{{ t }}_{{ n }}d,
        {% endfor %}
        {% endfor %}
        1 as _one
    from first_action
    group by 1, 2
),
any_action as (
    select repo_id, cohort_week,
        {% for n in [30, 60, 90] %}
        count(*) filter (where d <= {{ n }}) as n_any_{{ n }}d{{ ',' if not loop.last }}
        {% endfor %}
    from (select repo_id, actor_id, cohort_week, min(d) as d from first_action group by 1, 2, 3)
    group by 1, 2
)
select c.repo_id, c.cohort_week, c.n_stargazers,
    {% for t in ['fork', 'issue', 'pull_request', 'comment', 'any'] %}
    {% for n in [30, 60, 90] %}
    coalesce({{ 'aa' if t == 'any' else 'agg' }}.n_{{ t }}_{{ n }}d, 0)::double / c.n_stargazers as share_{{ t }}_{{ n }}d,
    {% endfor %}
    {% endfor %}
    {% for n in [30, 60, 90] %}
    (c.cohort_week + 7 + {{ n }} <= date '{{ var("events_end") }}') as is_mature_{{ n }}d{{ ',' if not loop.last }}
    {% endfor %}
from c
left join agg on agg.repo_id = c.repo_id and agg.cohort_week = c.cohort_week
left join any_action aa on aa.repo_id = c.repo_id and aa.cohort_week = c.cohort_week
