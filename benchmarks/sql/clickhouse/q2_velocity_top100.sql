-- Q2: top 100 repos by 7-day star velocity on 12 dates (window functions). Velocity is the sum of
-- stars in the 7 days up to and including the date, for repos with a star on that date.
WITH daily AS (
    SELECT repo_id, toDate(created_at) AS day, count() AS stars
    FROM file('{DATA}/WatchEvent/*.parquet', Parquet)
    GROUP BY repo_id, day
),
vel AS (
    SELECT repo_id, day,
           sum(stars) OVER (PARTITION BY repo_id ORDER BY day
                            RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) AS velocity_7d
    FROM daily
),
ranked AS (
    SELECT day, repo_id, velocity_7d,
           row_number() OVER (PARTITION BY day ORDER BY velocity_7d DESC, repo_id) AS rnk
    FROM vel
    WHERE day IN (SELECT toDate('2022-01-15') + toIntervalMonth(number) FROM numbers(12))
)
SELECT day, rnk, repo_id, velocity_7d FROM ranked WHERE rnk <= 100 ORDER BY day, rnk
