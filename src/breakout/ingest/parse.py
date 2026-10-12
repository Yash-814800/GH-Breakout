"""Parse one hourly GH Archive file into slim ``events`` rows and staged push rows.

DuckDB does the JSON work (``read_ndjson_objects``); nothing loads a whole file into Python.
Payload paths were verified against real samples in ``docs/schema_audit.md``; a path missing in
an era simply yields NULL (never imputed).
"""

from __future__ import annotations

import gzip
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa

from breakout.duck import connect
from breakout.logging import get_logger
from breakout.schema import (
    EVENTS_COLUMNS,
    EVENTS_SCHEMA,
    PUSH_ROWS_SCHEMA,
    SOURCE_HOURLY,
)

log = get_logger(__name__)

PUSH_TYPE = "PushEvent"
_J = "json"


def _s(path: str) -> str:
    return f"json_extract_string({_J}, '$.{path}')"


def _int(path: str, typ: str = "BIGINT") -> str:
    return f"TRY_CAST({_s(path)} AS {typ})"


_PR_NUMBER = (
    f"COALESCE({_int('payload.pull_request.number', 'INTEGER')}, "
    f"{_int('payload.number', 'INTEGER')})"
)


def _ts(path: str) -> str:
    return f"(TRY_CAST({_s(path)} AS TIMESTAMPTZ) AT TIME ZONE 'UTC')"


def _present(path: str) -> str:
    return f"COALESCE(json_type({_J}, '$.{path}'), 'NULL') <> 'NULL'"


# Event types that carry the generic ``payload.action`` column.
_ACTION_TYPES = (
    "WatchEvent",
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "ReleaseEvent",
)

_DETAIL_SQL = {
    "action": f"CASE WHEN etype IN ({', '.join(repr(t) for t in _ACTION_TYPES)}) "
    f"THEN {_s('payload.action')} END",
    "number": f"""CASE etype
        WHEN 'IssuesEvent' THEN {_int("payload.issue.number", "INTEGER")}
        WHEN 'IssueCommentEvent' THEN {_int("payload.issue.number", "INTEGER")}
        WHEN 'PullRequestEvent' THEN {_PR_NUMBER}
        WHEN 'PullRequestReviewEvent' THEN {_PR_NUMBER}
    END""",
    "is_pull_request": f"""CASE etype
        WHEN 'PullRequestEvent' THEN TRUE
        WHEN 'PullRequestReviewEvent' THEN TRUE
        WHEN 'IssuesEvent' THEN FALSE
        WHEN 'IssueCommentEvent' THEN {_present("payload.issue.pull_request")}
    END""",
    "target_user_id": f"""CASE etype
        WHEN 'IssuesEvent' THEN {_int("payload.issue.user.id")}
        WHEN 'IssueCommentEvent' THEN {_int("payload.issue.user.id")}
        WHEN 'PullRequestEvent' THEN {_int("payload.pull_request.user.id")}
        WHEN 'PullRequestReviewEvent' THEN {_int("payload.pull_request.user.id")}
    END""",
    "target_created_at": f"""CASE etype
        WHEN 'IssuesEvent' THEN {_ts("payload.issue.created_at")}
        WHEN 'IssueCommentEvent' THEN {_ts("payload.issue.created_at")}
        WHEN 'PullRequestEvent' THEN {_ts("payload.pull_request.created_at")}
        WHEN 'PullRequestReviewEvent' THEN {_ts("payload.pull_request.created_at")}
    END""",
    "pr_merged": f"""CASE WHEN etype = 'PullRequestEvent' AND {_s("payload.action")} = 'closed'
        THEN TRY_CAST({_s("payload.pull_request.merged")} AS BOOLEAN) END""",
    "review_state": f"CASE WHEN etype = 'PullRequestReviewEvent' "
    f"THEN {_s('payload.review.state')} END",
    "ref_type": f"CASE WHEN etype = 'CreateEvent' THEN {_s('payload.ref_type')} END",
    "forkee_repo_id": f"CASE WHEN etype = 'ForkEvent' THEN {_int('payload.forkee.id')} END",
    "release_prerelease": f"CASE WHEN etype = 'ReleaseEvent' "
    f"THEN TRY_CAST({_s('payload.release.prerelease')} AS BOOLEAN) END",
}


@dataclass
class ParseStats:
    lines_read: int = 0
    bad_json_lines: int = 0
    bad_ids: int = 0  # kept-type rows dropped for an unparsable id / actor / repo / created_at
    duplicates: int = 0
    out_of_window: int = 0  # created_at more than 1h outside the file's hour (kept, counted)
    kept_per_type: Counter[str] = field(default_factory=Counter)

    @property
    def rows_kept(self) -> int:
        return sum(self.kept_per_type.values())


@dataclass
class ParsedHour:
    events: pa.Table
    push_rows: pa.Table
    stats: ParseStats


def _count_lines(path: Path) -> int:
    n = 0
    tail_open = False
    with gzip.open(path, "rb") as fh:
        while chunk := fh.read(1 << 22):
            n += chunk.count(b"\n")
            tail_open = not chunk.endswith(b"\n")
    return n + (1 if tail_open else 0)


def parse_hour_file(
    path: Path,
    hour_ts: datetime,
    *,
    raw_types: list[str],
    aggregated_types: list[str] | None = None,
    source: str = SOURCE_HOURLY,
    ingested_at: datetime | None = None,
) -> ParsedHour:
    """Parse ``path`` (one gzip NDJSON hour). ``aggregated_types`` defaults to PushEvent only."""
    agg = aggregated_types if aggregated_types is not None else [PUSH_TYPE]
    if PUSH_TYPE in raw_types:
        raise ValueError("PushEvent is aggregated, not a raw type")
    hour = hour_ts.replace(tzinfo=None) if hour_ts.tzinfo is None else hour_ts.astimezone(UTC)
    hour = hour.replace(tzinfo=None)
    now = (ingested_at or datetime.now(UTC)).replace(tzinfo=None, microsecond=0)
    stats = ParseStats(lines_read=_count_lines(path))

    con = connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        all_types = [*raw_types, *agg]
        placeholders = ", ".join("?" for _ in all_types)
        con.execute(
            f"""
            CREATE TEMP TABLE base AS
            SELECT
                {_int("id")} AS event_id,
                {_s("type")} AS etype,
                {_ts("created_at")} AS created_at,
                {_int("repo.id")} AS repo_id,
                {_s("repo.name")} AS repo_name,
                {_int("actor.id")} AS actor_id,
                {_s("actor.login")} AS actor_login,
                {_int("org.id")} AS org_id,
                {", ".join(f"{expr} AS {name}" for name, expr in _DETAIL_SQL.items())}
            FROM read_ndjson_objects(?, compression = 'gzip', ignore_errors = true)
            WHERE {_s("type")} IN ({placeholders})
            """,
            [str(path), *all_types],
        )
        # with ignore_errors, a malformed line comes back as a NULL json row
        bad = con.execute(
            "SELECT count(*) FROM read_ndjson_objects(?, compression='gzip', ignore_errors=true) "
            "WHERE json IS NULL",
            [str(path)],
        ).fetchone()
        stats.bad_json_lines = bad[0] if bad else 0

        con.execute(
            """
            CREATE TEMP TABLE good AS
            SELECT * FROM base
            WHERE event_id IS NOT NULL AND created_at IS NOT NULL
              AND repo_id IS NOT NULL AND actor_id IS NOT NULL
            """
        )
        n_base = con.execute("SELECT count(*) FROM base").fetchone()[0]  # type: ignore[index]
        n_good = con.execute("SELECT count(*) FROM good").fetchone()[0]  # type: ignore[index]
        stats.bad_ids = n_base - n_good
        con.execute(
            """
            CREATE TEMP TABLE dedup AS
            SELECT * FROM good
            QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY created_at, etype) = 1
            """
        )
        n_dedup = con.execute("SELECT count(*) FROM dedup").fetchone()[0]  # type: ignore[index]
        stats.duplicates = n_good - n_dedup
        oow = con.execute(
            "SELECT count(*) FROM dedup WHERE created_at < ? OR created_at >= ?",
            [hour - timedelta(hours=1), hour + timedelta(hours=2)],
        ).fetchone()
        stats.out_of_window = oow[0] if oow else 0

        detail_cols = [c for c in _DETAIL_SQL]
        select_events = ", ".join(
            [
                "event_id",
                "etype AS event_type",
                "created_at",
                "repo_id",
                "repo_name",
                "actor_id",
                "actor_login",
                "org_id",
                "CAST(1 AS UTINYINT) AS detail_level",
                *detail_cols,
                "? AS source",
                "CAST(? AS TIMESTAMP) AS ingested_at",
            ]
        )
        types_ph = ", ".join("?" for _ in raw_types)
        events = con.execute(
            f"SELECT {select_events} FROM dedup WHERE etype IN ({types_ph}) "
            "ORDER BY repo_id, created_at, event_id",
            [source, now, *raw_types],
        ).to_arrow_table()
        push = con.execute(
            "SELECT event_id, repo_id, actor_id, created_at, repo_name, ? AS source FROM dedup "
            "WHERE etype = ? ORDER BY repo_id, created_at, event_id",
            [source, PUSH_TYPE],
        ).to_arrow_table()
    finally:
        con.close()

    assert events.column_names == EVENTS_COLUMNS
    events = events.cast(EVENTS_SCHEMA)
    push = push.select(PUSH_ROWS_SCHEMA.names).cast(PUSH_ROWS_SCHEMA)
    for etype, n in Counter(events.column("event_type").to_pylist()).items():
        stats.kept_per_type[etype] = n
    if push.num_rows:
        stats.kept_per_type[PUSH_TYPE] = push.num_rows
    if stats.out_of_window:
        log.warning("%s: %d events outside ±1h window", path.name, stats.out_of_window)
    return ParsedHour(events, push, stats)
