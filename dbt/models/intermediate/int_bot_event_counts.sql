{#
  Bot events per (repo_id, day) for star-active repos only (all kept event types, bot stars
  included): feeds the mirror-like share in int_repo_birth. Restricted to int_star_active_repos
  because bot events exist on tens of millions of repos and nothing else needs them (ADR-020).
#}
{% set types = ['ForkEvent', 'IssuesEvent', 'IssueCommentEvent', 'PullRequestEvent',
                'PullRequestReviewEvent', 'ReleaseEvent', 'CreateEvent', 'PublicEvent', 'WatchEvent'] %}
with bots as (select actor_id from {{ ref('stg_bot_actors') }}),
active as (select repo_id from {{ ref('int_star_active_repos') }})
{% for t in types %}
, t{{ loop.index }} as (
    select e.repo_id, e.created_at::date as day, count(*) as n_bot_events
    from {{ lake_events(t) }} as e
    semi join bots using (actor_id)
    semi join active using (repo_id)
    where {{ window_filter('e.created_at') }}
    group by 1, 2
)
{% endfor %}
, p as (
    select x.repo_id, x.day, sum(x.n_pushes) as n_bot_events
    from {{ lake_events('push_daily') }} as x
    semi join bots using (actor_id)
    semi join active using (repo_id)
    where x.day >= date '{{ var("events_start") }}' and x.day < date '{{ var("events_end") }}'
    group by 1, 2
)
select repo_id, day, sum(n_bot_events)::bigint as n_bot_events
from (
    {% for t in types %}select * from t{{ loop.index }} union all
    {% endfor %}
    select * from p
)
group by 1, 2
