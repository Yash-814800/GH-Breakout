-- Q1: daily stars per repo for the year (GROUP BY). The final aggregate keeps the result small and
-- comparable; the GROUP BY over every (repo, day) is the work being measured.
WITH daily AS (
    SELECT repo_id, created_at::DATE AS day, count(*) AS stars
    FROM read_parquet('{DATA}/WatchEvent/*.parquet')
    GROUP BY repo_id, day
)
SELECT count(*) AS repo_days,
       sum(stars) AS total_stars,
       max(stars) AS max_stars,
       count(DISTINCT repo_id) AS repos,
       sum(stars * stars) AS sum_sq
FROM daily
