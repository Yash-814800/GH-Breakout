-- Q6b: approximate distinct count per month (HyperLogLog).
SELECT date_trunc('month', created_at)::DATE AS month, approx_count_distinct(actor_id) AS actors
FROM read_parquet('{DATA}/WatchEvent/*.parquet')
GROUP BY month ORDER BY month
