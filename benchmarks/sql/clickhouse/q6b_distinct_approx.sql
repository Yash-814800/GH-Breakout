-- Q6b: approximate distinct count per month (uniq: adaptive sampling).
SELECT toDate(toStartOfMonth(created_at)) AS month, uniq(actor_id) AS actors
FROM file('{DATA}/WatchEvent/*.parquet', Parquet)
GROUP BY month ORDER BY month
