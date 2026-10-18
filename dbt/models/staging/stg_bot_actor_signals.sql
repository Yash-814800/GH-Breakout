{{ config(materialized='incremental', unique_key=['month', 'actor_id'], incremental_strategy='delete+insert') }}

{#
  Per (month, actor_id) bot evidence, kept only for actors that have some:
    bot_like_login  a login containing "bot" or in the known_bots seed (rules applied in stg_bot_actors)
    n_busy_days     UTC days in the month with > 1,000 non-star events (pushes counted by n_pushes)
  Two passes per month (monthly totals, then day counts for the few busy actors) keep memory bounded.
  A plan with many months is large, so `breakout build history` calls this model once per year with
  --vars (ADR-020); the model is incremental on (month, actor_id) and rebuilds exactly the months of
  its window.
#}

{% set types = ['ForkEvent', 'IssuesEvent', 'IssueCommentEvent', 'PullRequestEvent',
                'PullRequestReviewEvent', 'ReleaseEvent', 'CreateEvent', 'PublicEvent'] %}

with
{% for ys, ye, y in window_months() %}
{% set union_sql %}
  {% for t in types %}
  select actor_id,
         case when actor_login ilike '%bot%'
                or lower(actor_login) in (select lower(login) from {{ ref('known_bots') }})
              then actor_login end as actor_login,
         created_at::date as day, 1 as n
  from {{ lake_events(t, y, y) }}
  where created_at >= greatest(timestamp '{{ ys }}', timestamp '{{ var("events_start") }}')
    and created_at < least(timestamp '{{ ye }}', timestamp '{{ var("events_end") }}')
  union all
  {% endfor %}
  select actor_id, null as actor_login, day, n_pushes as n from {{ lake_events('push_daily', y, y) }}
  where day >= greatest(date '{{ ys }}', date '{{ var("events_start") }}')
    and day < least(date '{{ ye }}', date '{{ var("events_end") }}')
{% endset %}
m{{ loop.index }}_totals as (
  select actor_id, sum(n) as n_events, max(actor_login) as bot_like_login
  from ({{ union_sql }})
  group by actor_id
),
m{{ loop.index }}_days as (
  select u.actor_id, count(*) as n_busy_days
  from (
    select u.actor_id, u.day
    from ({{ union_sql }}) u
    semi join (select actor_id from m{{ loop.index }}_totals where n_events > 1000) b using (actor_id)
    group by u.actor_id, u.day
    having sum(u.n) > 1000
  ) u
  group by u.actor_id
),
m{{ loop.index }} as (
  select date '{{ ys }}' as month, t.actor_id, t.bot_like_login, coalesce(d.n_busy_days, 0)::integer as n_busy_days
  from m{{ loop.index }}_totals t
  left join m{{ loop.index }}_days d using (actor_id)
  where t.bot_like_login is not null or d.n_busy_days > 0
){{ ',' if not loop.last }}
{% endfor %}
{% for ys, ye, y in window_months() %}
select * from m{{ loop.index }}{{ ' union all' if not loop.last }}
{% endfor %}
