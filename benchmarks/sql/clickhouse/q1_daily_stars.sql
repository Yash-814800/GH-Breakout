-- Q1: daily stars per repo for the year (GROUP BY). The final aggregate keeps the result small and
-- comparable; the GROUP BY over every (repo, day) is the work being measured.
WITH daily AS (
    SELECT repo_id, toDate(created_at) AS day, count() AS stars
    FROM file('{DATA}/WatchEvent/*.parquet', Parquet)
    GROUP BY repo_id, day
)
SELECT count() AS repo_days,
       sum(stars) AS total_stars,
       max(stars) AS max_stars,
       uniqExact(repo_id) AS repos,
       sum(stars * stars) AS sum_sq
FROM daily
