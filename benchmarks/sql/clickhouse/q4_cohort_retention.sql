-- Q4: weekly stargazer cohort retention (self-join stars to later actions).
-- Cohort = week of a stargazer's first star of a repo; retained = the same actor commented on or
-- opened/updated a pull request in that repo within 28 days after the star.
WITH stars AS (
    SELECT repo_id, actor_id, min(created_at) AS starred_at
    FROM file('{DATA}/WatchEvent/*.parquet', Parquet)
    GROUP BY repo_id, actor_id
),
acts AS (
    SELECT repo_id, actor_id, created_at AS at FROM file('{DATA}/IssueCommentEvent/*.parquet', Parquet)
    UNION ALL
    SELECT repo_id, actor_id, created_at AS at FROM file('{DATA}/PullRequestEvent/*.parquet', Parquet)
),
retained AS (
    SELECT s.repo_id AS repo_id, s.actor_id AS actor_id, 1 AS r
    FROM acts a INNER JOIN stars s ON a.repo_id = s.repo_id AND a.actor_id = s.actor_id
    WHERE a.at > s.starred_at AND a.at <= s.starred_at + INTERVAL 28 DAY
    GROUP BY s.repo_id, s.actor_id
)
SELECT toDate(toMonday(s.starred_at)) AS cohort_week,
       count() AS stargazers,
       sum(t.r) AS retained_28d
FROM stars s LEFT JOIN retained t ON t.repo_id = s.repo_id AND t.actor_id = s.actor_id
GROUP BY cohort_week ORDER BY cohort_week
