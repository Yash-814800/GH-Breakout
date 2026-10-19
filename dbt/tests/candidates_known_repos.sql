-- Hand-picked from the real data (Phase 6 build): on Monday 2019-11-25 connor4312/cockatiel
-- (repo_id 221853525, 9 days old, 177 stars in its first week) and
-- alirezadir/Production-Level-Deep-Learning (222780595, 6 days old, 161 stars) were candidates, and
-- both broke out (610 and 1603 stars in the next 30 days). Skipped when the build window does not
-- contain that snapshot date.
with expected as (
    select * from (values (221853525, date '2019-11-25'), (222780595, date '2019-11-25')) t(repo_id, snapshot_date)
)
select e.repo_id, e.snapshot_date
from expected e
where exists (select 1 from {{ ref('mart_snapshot_dates') }} s where s.snapshot_date = e.snapshot_date and s.is_label_matured)
  and not exists (
      select 1 from {{ ref('mart_labels') }} l
      where l.repo_id = e.repo_id and l.snapshot_date = e.snapshot_date and l.breakout_rel
  )
