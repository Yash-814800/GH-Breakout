{{ config(severity='warn') }}
-- positive rate per matured snapshot should be 0.2% .. 2% (quiet early years can fall outside: warn only)
select snapshot_date, count(*) as n, avg(breakout_rel::int) as positive_rate
from {{ ref('mart_labels') }}
group by 1
having avg(breakout_rel::int) < 0.002 or avg(breakout_rel::int) > 0.02
