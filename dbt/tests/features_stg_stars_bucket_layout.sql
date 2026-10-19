{#
  feat_star_dynamics prunes stg_stars with `bucket = repo_id % 32` (literal 32). The staging table must have
  been built with 32 buckets; a table built with another n_buckets would silently give NULL hour shares.
  Sampled: a full scan of 477 M rows is not needed to catch a wrong layout.
#}
select repo_id, bucket
from {{ ref('stg_stars') }}
where repo_id % 1009 = 0 and bucket <> repo_id % 32
limit 10
