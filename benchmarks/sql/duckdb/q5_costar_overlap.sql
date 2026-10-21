-- Q5: co-star overlap for the 100 most-starred repos of the year (self-join on actor).
-- For every pair of the 100, the number of actors who starred both; the 50 largest overlaps.
WITH seeds AS (
    SELECT repo_id FROM read_parquet('{DATA}/WatchEvent/*.parquet')
    GROUP BY repo_id ORDER BY count(*) DESC, repo_id LIMIT 100
),
st AS (
    SELECT DISTINCT repo_id, actor_id
    FROM read_parquet('{DATA}/WatchEvent/*.parquet')
    WHERE repo_id IN (SELECT repo_id FROM seeds)
)
SELECT a.repo_id AS repo_a, b.repo_id AS repo_b, count(*) AS overlap
FROM st a JOIN st b ON a.actor_id = b.actor_id
WHERE a.repo_id < b.repo_id
GROUP BY repo_a, repo_b
ORDER BY overlap DESC, repo_a, repo_b
LIMIT 50
