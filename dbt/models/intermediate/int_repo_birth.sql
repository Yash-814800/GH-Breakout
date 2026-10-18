{#
  Grain repo_id, for star-active repos (int_star_active_repos; ADR-020).
  birth_at = max(public time, COALESCE(api created_at, CreateEvent repository, first event)), where
  the public time only counts if it is not after the first star: a repo starred before its PublicEvent
  was already public and has been re-published (ADR-020).
  Caveats: first_event_at is left-censored at events_start. A repo with no API created_at whose first
  event falls within 30 days of events_start is flagged is_left_censored and is never "young".
  Bot events are excluded from first_event_at (staging drops them).
#}
with active as (select repo_id from {{ ref('int_star_active_repos') }}),
ev as (
    select repo_id, min(first_at) as first_event_at
    from {{ ref('int_active_repo_event_days') }}
    group by 1
),
stars as (
    select repo_id, min(starred_at) as first_star_at from {{ ref('stg_stars') }}
    semi join active using (repo_id) group by 1
),
created as (
    select c.repo_id, min(c.created_at) as created_repo_event_at
    from {{ ref('stg_creates') }} c semi join active using (repo_id)
    where c.ref_type = 'repository' group by 1
),
public as (
    select p.repo_id, min(p.created_at) as made_public_at
    from {{ ref('stg_public_events') }} p semi join active using (repo_id) group by 1
),
fork_children as (
    select distinct forkee_repo_id as repo_id from {{ ref('stg_forks') }}
    where forkee_repo_id in (select repo_id from active)
),
base as (
    select
        a.repo_id,
        ev.first_event_at,
        s.first_star_at,
        c.created_repo_event_at,
        p.made_public_at,
        m.api_created_at,
        coalesce(m.status = 'ok', false) as has_metadata,
        coalesce(m.is_fork, false) as meta_is_fork,
        coalesce(m.is_mirror, false) as meta_is_mirror,
        fc.repo_id is not null as is_forkee,
        coalesce(m.api_created_at, c.created_repo_event_at, ev.first_event_at) as raw_birth_at,
        (p.made_public_at is not null and p.made_public_at > coalesce(m.api_created_at, c.created_repo_event_at, ev.first_event_at)
            and (s.first_star_at is null or p.made_public_at <= s.first_star_at)) as public_applies,
        case when m.api_created_at is not null then 'api'
             when c.created_repo_event_at is not null then 'create_event'
             else 'first_event' end as raw_birth_source
    from active a
    left join ev using (repo_id)
    left join stars s using (repo_id)
    left join created c using (repo_id)
    left join public p using (repo_id)
    left join fork_children fc using (repo_id)
    left join {{ ref('stg_repo_metadata') }} m using (repo_id)
),
bot30 as (
    select b.repo_id,
           sum(bc.n_bot_events) as n_bot_events_30d
    from base b
    join {{ ref('int_bot_event_counts') }} bc on bc.repo_id = b.repo_id
        and bc.day >= b.raw_birth_at::date and bc.day < b.raw_birth_at::date + 30
    group by 1
),
human30 as (
    select b.repo_id, sum(e.n_events) as n_events_30d
    from base b
    join {{ ref('int_active_repo_event_days') }} e on e.repo_id = b.repo_id
        and e.day >= b.raw_birth_at::date and e.day < b.raw_birth_at::date + 30
    group by 1
)
select
    b.repo_id,
    b.first_event_at,
    b.first_star_at,
    b.created_repo_event_at,
    b.made_public_at,
    b.api_created_at,
    case when b.public_applies then b.made_public_at else b.raw_birth_at end as birth_at,
    case when b.public_applies then 'public_event' else b.raw_birth_source end as birth_source,
    (b.meta_is_fork or b.is_forkee) as is_fork,
    (b.meta_is_mirror
        or coalesce(bt.n_bot_events_30d, 0)
           > 0.8 * (coalesce(bt.n_bot_events_30d, 0) + coalesce(h.n_events_30d, 0))
           and coalesce(bt.n_bot_events_30d, 0) > 0) as is_mirror_like,
    b.has_metadata,
    (b.api_created_at is null
        and b.first_event_at < timestamp '{{ var("events_start") }}' + interval 30 day) as is_left_censored
from base b
left join bot30 bt using (repo_id)
left join human30 h using (repo_id)
