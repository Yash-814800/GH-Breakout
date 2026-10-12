"""BigQuery query builders for the historical backfill (plain f-strings, validated inputs).

Billing is by bytes of the *columns referenced* across all rows of the tables touched:
``WHERE type = ...`` and ``LIMIT`` do not reduce it, and referencing ``payload`` once scans the
whole column. So all detail fields for a table come from ONE query, spine mode never mentions
``payload`` (enforced by a unit test), and PushEvent rows ride along in the same query (their
spine columns are already scanned) to be aggregated into ``push_daily`` locally.

Payload paths and fallbacks mirror ``breakout.ingest.parse`` / ``docs/schema_audit.md``.
"""

from __future__ import annotations

import re
from datetime import date

MODES = ("spine", "full")
DAY_TABLE_WILDCARD = "`githubarchive.day.20*`"

_TYPE_RE = re.compile(r"^[A-Za-z]+Event$")

_ACTION_TYPES = (
    "WatchEvent",
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "ReleaseEvent",
)


def _jv(path: str) -> str:
    return f"JSON_VALUE(payload, '$.{path}')"


def _int(path: str) -> str:
    return f"SAFE_CAST({_jv(path)} AS INT64)"


def _present(path: str) -> str:
    q = f"JSON_QUERY(payload, '$.{path}')"
    return f"({q} IS NOT NULL AND {q} != 'null')"


# column name -> (full-mode expression, spine-mode typed NULL)
DETAIL_COLUMNS: dict[str, tuple[str, str]] = {
    "action": (
        "CASE WHEN type IN ("
        + ", ".join(f"'{t}'" for t in _ACTION_TYPES)
        + f") THEN {_jv('action')} END",
        "CAST(NULL AS STRING)",
    ),
    "number": (
        f"""CASE
      WHEN type IN ('IssuesEvent', 'IssueCommentEvent') THEN {_int("issue.number")}
      WHEN type IN ('PullRequestEvent', 'PullRequestReviewEvent')
        THEN COALESCE({_int("pull_request.number")}, {_int("number")})
    END""",
        "CAST(NULL AS INT64)",
    ),
    "is_pull_request": (
        f"""CASE
      WHEN type IN ('PullRequestEvent', 'PullRequestReviewEvent') THEN TRUE
      WHEN type = 'IssuesEvent' THEN FALSE
      WHEN type = 'IssueCommentEvent' THEN {_present("issue.pull_request")}
    END""",
        "CAST(NULL AS BOOL)",
    ),
    "target_user_id": (
        f"""CASE
      WHEN type IN ('IssuesEvent', 'IssueCommentEvent') THEN {_int("issue.user.id")}
      WHEN type IN ('PullRequestEvent', 'PullRequestReviewEvent')
        THEN {_int("pull_request.user.id")}
    END""",
        "CAST(NULL AS INT64)",
    ),
    "target_created_at": (
        f"""CASE
      WHEN type IN ('IssuesEvent', 'IssueCommentEvent')
        THEN SAFE_CAST({_jv("issue.created_at")} AS TIMESTAMP)
      WHEN type IN ('PullRequestEvent', 'PullRequestReviewEvent')
        THEN SAFE_CAST({_jv("pull_request.created_at")} AS TIMESTAMP)
    END""",
        "CAST(NULL AS TIMESTAMP)",
    ),
    "pr_merged": (
        f"""CASE WHEN type = 'PullRequestEvent' AND {_jv("action")} = 'closed'
      THEN SAFE_CAST({_jv("pull_request.merged")} AS BOOL) END""",
        "CAST(NULL AS BOOL)",
    ),
    "review_state": (
        f"CASE WHEN type = 'PullRequestReviewEvent' THEN {_jv('review.state')} END",
        "CAST(NULL AS STRING)",
    ),
    "ref_type": (
        f"CASE WHEN type = 'CreateEvent' THEN {_jv('ref_type')} END",
        "CAST(NULL AS STRING)",
    ),
    "forkee_repo_id": (
        f"CASE WHEN type = 'ForkEvent' THEN {_int('forkee.id')} END",
        "CAST(NULL AS INT64)",
    ),
    "release_prerelease": (
        f"CASE WHEN type = 'ReleaseEvent' THEN SAFE_CAST({_jv('release.prerelease')} AS BOOL) END",
        "CAST(NULL AS BOOL)",
    ),
}

SPINE_SELECT = """\
  SAFE_CAST(id AS INT64) AS event_id,
  type AS event_type,
  created_at,
  repo.id AS repo_id,
  repo.name AS repo_name,
  actor.id AS actor_id,
  actor.login AS actor_login,
  org.id AS org_id"""


def day_table_expr(start: date, end: date) -> str:
    """Day-table wildcard restricted to ``[start, end]`` (inclusive), 6-digit ``YYMMDD`` suffixes.

    Note: ``_TABLE_SUFFIX`` is what follows the wildcard prefix ``20``, so suffixes are ``YYMMDD``.
    """
    if end < start or not (2000 <= start.year <= 2099 and 2000 <= end.year <= 2099):
        raise ValueError("bad date range")
    return f"{DAY_TABLE_WILDCARD}\nWHERE _TABLE_SUFFIX BETWEEN '{start:%y%m%d}' AND '{end:%y%m%d}'"


def raw_events_sql(start: date, end: date, mode: str, *, include_push: bool = True) -> str:
    """One row per event for ``@raw_types`` (+ PushEvent spine rows when ``include_push``).

    The caller binds ``@raw_types`` (ARRAY<STRING>) as a query parameter; PushEvent is added in
    SQL so aggregation into ``push_daily`` happens locally from the same scan.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    detail = [
        f"  {expr if mode == 'full' else null} AS {name}"
        for name, (expr, null) in DETAIL_COLUMNS.items()
    ]
    types = "type IN UNNEST(@raw_types)"
    if include_push:
        types = "(type IN UNNEST(@raw_types) OR type = 'PushEvent')"
    return (
        "SELECT\n"
        + SPINE_SELECT
        + ",\n"
        + ",\n".join(detail)
        + f"\nFROM {day_table_expr(start, end)}\n  AND {types}"
    )


def push_daily_sql(start: date, end: date) -> str:
    """Stand-alone push aggregate (kept for comparison; the combined query makes it redundant)."""
    return (
        "SELECT repo.id AS repo_id, actor.id AS actor_id, DATE(created_at) AS day,\n"
        "  COUNT(*) AS n_pushes, ANY_VALUE(repo.name) AS repo_name\n"
        f"FROM {day_table_expr(start, end)}\n  AND type = 'PushEvent'\n"
        "GROUP BY 1, 2, 3"
    )


def validate_types(types: list[str]) -> list[str]:
    for t in types:
        if not _TYPE_RE.match(t):
            raise ValueError(f"suspicious event type: {t!r}")
    return types
