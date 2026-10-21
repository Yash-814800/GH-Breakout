{{ config(materialized='view') }}
{#
  Grain (repo_id, snapshot_date) for candidates.
  Transparent suspicious-growth score detecting anomalous stargazer distributions and star spikes (Phase 11, §11.1).
  Robust z-scores per snapshot date clipped to [0, 6], mapped to 0-100 via historical empirical CDF.
#}
with base as (
    select c.bucket, c.repo_id, c.snapshot_date, c.stars_14d,
           coalesce(sg.sg_share_account_lt_30d, 0.0) as s_new_accounts,
           coalesce(sg.sg_share_zero_prior_activity, 0.0) as s_inactive,
           coalesce(sg.sg_share_bulk_starrers, 0.0) as s_bulk,
           coalesce(sd.star_max_hour_share_7d, 0.0) as s_burst,
           0.0 as s_lockstep,
           1.0 - least(1.0, (
               coalesce(fa.forks_14d, 0) +
               coalesce(fa.issue_events_14d, 0) +
               coalesce(fa.comment_events_14d, 0) +
               coalesce(fa.pr_events_14d, 0)
           )::double / (0.05 * greatest(c.stars_14d, 1))) as s_no_engagement
    from {{ ref('mart_candidates') }} c
    left join {{ ref('feat_stargazers') }} sg on sg.repo_id = c.repo_id and sg.snapshot_date = c.snapshot_date
    left join {{ ref('feat_star_dynamics') }} sd on sd.repo_id = c.repo_id and sd.snapshot_date = c.snapshot_date
    left join {{ ref('feat_activity') }} fa on fa.repo_id = c.repo_id and fa.snapshot_date = c.snapshot_date
),
meds as (
    select *,
           median(s_new_accounts) over (partition by snapshot_date) as med_new,
           median(s_inactive) over (partition by snapshot_date) as med_inact,
           median(s_bulk) over (partition by snapshot_date) as med_bulk,
           median(s_burst) over (partition by snapshot_date) as med_burst,
           median(s_no_engagement) over (partition by snapshot_date) as med_no_eng
    from base
),
mads as (
    select *,
           greatest(median(abs(s_new_accounts - med_new)) over (partition by snapshot_date), 1.2533 * avg(abs(s_new_accounts - med_new)) over (partition by snapshot_date)) as mad_new,
           greatest(median(abs(s_inactive - med_inact)) over (partition by snapshot_date), 1.2533 * avg(abs(s_inactive - med_inact)) over (partition by snapshot_date)) as mad_inact,
           greatest(median(abs(s_bulk - med_bulk)) over (partition by snapshot_date), 1.2533 * avg(abs(s_bulk - med_bulk)) over (partition by snapshot_date)) as mad_bulk,
           greatest(median(abs(s_burst - med_burst)) over (partition by snapshot_date), 1.2533 * avg(abs(s_burst - med_burst)) over (partition by snapshot_date)) as mad_burst,
           greatest(median(abs(s_no_engagement - med_no_eng)) over (partition by snapshot_date), 1.2533 * avg(abs(s_no_engagement - med_no_eng)) over (partition by snapshot_date)) as mad_no_eng
    from meds
),
zscores as (
    select bucket, repo_id, snapshot_date,
           s_new_accounts, s_inactive, s_bulk, s_burst, s_lockstep, s_no_engagement,
           case when mad_new > 1e-4 then least(6.0, greatest(0.0, (s_new_accounts - med_new) / (1.4826 * mad_new))) else 0.0 end as z_new,
           case when mad_inact > 1e-4 then least(6.0, greatest(0.0, (s_inactive - med_inact) / (1.4826 * mad_inact))) else 0.0 end as z_inact,
           case when mad_bulk > 1e-4 then least(6.0, greatest(0.0, (s_bulk - med_bulk) / (1.4826 * mad_bulk))) else 0.0 end as z_bulk,
           case when mad_burst > 1e-4 then least(6.0, greatest(0.0, (s_burst - med_burst) / (1.4826 * mad_burst))) else 0.0 end as z_burst,
           case when mad_no_eng > 1e-4 then least(6.0, greatest(0.0, (s_no_engagement - med_no_eng) / (1.4826 * mad_no_eng))) else 0.0 end as z_no_eng
    from mads
),
scored as (
    select bucket, repo_id, snapshot_date,
           s_new_accounts, s_inactive, s_bulk, s_burst, s_lockstep, s_no_engagement,
           (z_new + z_inact + z_bulk + z_burst + z_no_eng) / 5.0 as raw_score
    from zscores
),
ranked as (
    select *,
           round(percent_rank() over (order by raw_score) * 100.0, 1) as suspicion_score
    from scored
)
select
    bucket,
    repo_id,
    snapshot_date,
    round(s_new_accounts, 4) as s_new_accounts,
    round(s_inactive, 4) as s_inactive,
    round(s_bulk, 4) as s_bulk,
    round(s_burst, 4) as s_burst,
    round(s_lockstep, 4) as s_lockstep,
    round(s_no_engagement, 4) as s_no_engagement,
    round(raw_score, 4) as raw_score,
    suspicion_score,
    case
        when suspicion_score >= 98.0 then 'high'
        when suspicion_score >= 90.0 then 'medium'
        else 'low'
    end as suspicion_level
from ranked
