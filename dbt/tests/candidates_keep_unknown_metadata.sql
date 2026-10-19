{#
  ADR-017/021: a repo whose metadata is unknown (not_found, or never fetched, which is every repo created
  after the trusted era) is still a candidate. A NULL in the bot-owner `NOT (... or owner_id in (...))`
  predicate once dropped all of them (and with them every live candidate). Fails when a sizeable candidate
  table has no candidate without metadata.
#}
select 'no candidate without metadata' as problem
from (select count(*) as n_all from {{ ref('mart_candidates') }}) a
where n_all > 1000
  and not exists (
      select 1 from {{ ref('mart_candidates') }} c
      anti join {{ ref('stg_repo_metadata') }} m on m.repo_id = c.repo_id and m.status = 'ok'
  )
