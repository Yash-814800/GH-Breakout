-- Q4: weekly stargazer cohort retention (self-join stars to later actions).
-- Cohort = week of a stargazer's first star of a repo; retained = the same actor commented on or
-- opened/updated a pull request in that repo within 28 days after the star.
WITH stars AS (
    SELECT repo_id, actor_id, min(created_at) AS starred_at
    FROM read_parquet('{DATA}/WatchEvent/*.parquet')
    GROUP BY repo_id, actor_id
),
acts AS (
    SELECT repo_id, actor_id, created_at AS at FROM read_parquet('{DATA}/IssueCommentEvent/*.parquet')
    UNION ALL
    SELECT repo_id, actor_id, created_at AS at FROM read_parquet('{DATA}/PullRequestEvent/*.parquet')
),
retained AS (
    SELECT s.repo_id, s.actor_id, 1 AS r
    FROM stars s JOIN acts a ON a.repo_id = s.repo_id AND a.actor_id = s.actor_id
    WHERE a.at > s.starred_at AND a.at <= s.starred_at + INTERVAL 28 DAY
    GROUP BY s.repo_id, s.actor_id
)
SELECT date_trunc('week', s.starred_at)::DATE AS cohort_week,
       count(*) AS stargazers,
       sum(coalesce(t.r, 0)) AS retained_28d
FROM stars s LEFT JOIN retained t ON t.repo_id = s.repo_id AND t.actor_id = s.actor_id
GROUP BY cohort_week ORDER BY cohort_week
