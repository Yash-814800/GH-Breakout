-- Q2: top 100 repos by 7-day star velocity on 12 dates (window functions). Velocity is the sum of
-- stars in the 7 days up to and including the date, for repos with a star on that date.
WITH daily AS (
    SELECT repo_id, created_at::DATE AS day, count(*) AS stars
    FROM read_parquet('{DATA}/WatchEvent/*.parquet')
    GROUP BY repo_id, day
),
vel AS (
    SELECT repo_id, day,
           sum(stars) OVER (PARTITION BY repo_id ORDER BY day
                            RANGE BETWEEN INTERVAL 6 DAYS PRECEDING AND CURRENT ROW) AS velocity_7d
    FROM daily
),
ranked AS (
    SELECT day, repo_id, velocity_7d,
           row_number() OVER (PARTITION BY day ORDER BY velocity_7d DESC, repo_id) AS rnk
    FROM vel
    WHERE day IN (SELECT DATE '2022-01-01' + INTERVAL (m * 1) MONTH + INTERVAL 14 DAY
                  FROM range(0, 12) t(m))
)
SELECT day, rnk, repo_id, velocity_7d FROM ranked WHERE rnk <= 100 ORDER BY day, rnk
