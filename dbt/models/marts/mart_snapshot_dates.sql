{#
  Snapshot dates D ("the world as known at D 00:00 UTC", CLAUDE.md section 5).
    weekly_history  every training.snapshot_weekday (0 = Monday) from training.first_snapshot up to
                    the last date <= latest fully ingested day + 1
    single          exactly var('snapshot_date') (live scoring and tests)
  is_label_matured: D + horizon_days <= latest_ingested_day + 1, i.e. the whole label window
  [D, D + horizon) lies on ingested days. Labels and training use matured dates only.
#}
with latest as (select {{ latest_ingested_day() }} as latest_day),
dates as (
    {% if var('snapshot_dates_mode') == 'single' %}
    select date '{{ var("snapshot_date") }}' as snapshot_date
    {% else %}
    select d::date as snapshot_date
    from latest,
         generate_series(date '{{ var("first_snapshot") }}', latest.latest_day + 1, interval 1 day) t(d)
    where isodow(d) = {{ var('snapshot_weekday') }} + 1
    {% endif %}
)
select
    snapshot_date,
    snapshot_date + {{ var('horizon_days') }} <= latest_day + 1 as is_label_matured,
    latest_day as latest_ingested_day
from dates, latest
