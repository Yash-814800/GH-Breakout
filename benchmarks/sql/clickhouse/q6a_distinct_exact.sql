-- Q6a: exact COUNT(DISTINCT actor_id) per month.
SELECT toDate(toStartOfMonth(created_at)) AS month, uniqExact(actor_id) AS actors
FROM file('{DATA}/WatchEvent/*.parquet', Parquet)
GROUP BY month ORDER BY month
