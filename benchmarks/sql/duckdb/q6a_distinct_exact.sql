-- Q6a: exact COUNT(DISTINCT actor_id) per month.
SELECT date_trunc('month', created_at)::DATE AS month, count(DISTINCT actor_id) AS actors
FROM read_parquet('{DATA}/WatchEvent/*.parquet')
GROUP BY month ORDER BY month
