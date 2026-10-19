{#
  Latest fully ingested UTC day, as a SQL scalar subquery.
  The newest star in stg_stars (within the events window) tells how far ingestion got. Hourly files
  arrive whole, so a day is complete when the newest star is in hour 23 of it; otherwise the day
  before is the last complete one. The result never exceeds events_end - 1 day.
#}
{% macro latest_ingested_day() %}
(
    select least(
        date '{{ var("events_end") }}' - 1,
        case when hour(m) = 23 then m::date else m::date - 1 end
    )
    from (select max(starred_at) as m from {{ ref('stg_stars') }}
          where {{ window_filter('starred_at') }})
)
{% endmacro %}
