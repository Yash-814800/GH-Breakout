-- Q3: sessionization of comment activity with a 30-minute gap (LAG + running sum).
-- A session is a run of comments by one actor in one repository with gaps of at most 30 minutes.
WITH c AS (
    SELECT repo_id, actor_id, created_at, event_id,
           row_number() OVER w AS rn,
           lagInFrame(created_at) OVER w AS prev_at
    FROM file('{DATA}/IssueCommentEvent/*.parquet', Parquet)
    WINDOW w AS (PARTITION BY repo_id, actor_id ORDER BY created_at, event_id
                 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
),
flagged AS (
    SELECT repo_id, actor_id, created_at, event_id,
           if(rn = 1 OR dateDiff('second', prev_at, created_at) > 1800, 1, 0) AS is_new
    FROM c
),
numbered AS (
    SELECT repo_id, actor_id, created_at,
           sum(is_new) OVER (PARTITION BY repo_id, actor_id ORDER BY created_at, event_id
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_no
    FROM flagged
),
sessions AS (
    SELECT repo_id, actor_id, session_no, count() AS n_events,
           dateDiff('second', min(created_at), max(created_at)) AS duration_s
    FROM numbered
    GROUP BY repo_id, actor_id, session_no
)
SELECT count() AS sessions, sum(n_events) AS events, max(n_events) AS max_events,
       sum(duration_s) AS total_duration_s, uniqExact((repo_id, actor_id)) AS pairs
FROM sessions
