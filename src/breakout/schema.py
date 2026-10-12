"""Slim event schema: the single source of truth for BigQuery backfill and hourly ingest.

Timestamps are naive UTC ``TIMESTAMP`` (ADR-005, ADR-007); dates are ``DATE``.
Bump ``SCHEMA_VERSION`` when columns change and ``PARSER_VERSION`` whenever parsing logic
changes (the hourly manifest uses it to decide what to re-ingest).
"""

from __future__ import annotations

import pyarrow as pa

SCHEMA_VERSION = 1
PARSER_VERSION = 1

SOURCE_BQ = "bq"
SOURCE_HOURLY = "hourly"

# (name, duckdb type, nullable, pyarrow type)
_EVENTS_COLUMNS: list[tuple[str, str, bool, pa.DataType]] = [
    ("event_id", "BIGINT", False, pa.int64()),
    ("event_type", "VARCHAR", False, pa.string()),
    ("created_at", "TIMESTAMP", False, pa.timestamp("us")),
    ("repo_id", "BIGINT", False, pa.int64()),
    ("repo_name", "VARCHAR", True, pa.string()),
    ("actor_id", "BIGINT", False, pa.int64()),
    ("actor_login", "VARCHAR", True, pa.string()),
    ("org_id", "BIGINT", True, pa.int64()),
    ("detail_level", "UTINYINT", False, pa.uint8()),
    ("action", "VARCHAR", True, pa.string()),
    ("number", "INTEGER", True, pa.int32()),
    ("is_pull_request", "BOOLEAN", True, pa.bool_()),
    ("target_user_id", "BIGINT", True, pa.int64()),
    ("target_created_at", "TIMESTAMP", True, pa.timestamp("us")),
    ("pr_merged", "BOOLEAN", True, pa.bool_()),
    ("review_state", "VARCHAR", True, pa.string()),
    ("ref_type", "VARCHAR", True, pa.string()),
    ("forkee_repo_id", "BIGINT", True, pa.int64()),
    ("release_prerelease", "BOOLEAN", True, pa.bool_()),
    ("source", "VARCHAR", False, pa.string()),
    ("ingested_at", "TIMESTAMP", False, pa.timestamp("us")),
]

_PUSH_DAILY_COLUMNS: list[tuple[str, str, bool, pa.DataType]] = [
    ("repo_id", "BIGINT", False, pa.int64()),
    ("actor_id", "BIGINT", False, pa.int64()),
    ("day", "DATE", False, pa.date32()),
    ("n_pushes", "INTEGER", False, pa.int32()),
    ("repo_name", "VARCHAR", True, pa.string()),
    ("source", "VARCHAR", False, pa.string()),
    ("ingested_at", "TIMESTAMP", False, pa.timestamp("us")),
]

# Rows staged per hour for PushEvent, before daily aggregation (not a lake table).
_PUSH_ROWS_COLUMNS: list[tuple[str, str, bool, pa.DataType]] = [
    ("event_id", "BIGINT", False, pa.int64()),
    ("repo_id", "BIGINT", False, pa.int64()),
    ("actor_id", "BIGINT", False, pa.int64()),
    ("created_at", "TIMESTAMP", False, pa.timestamp("us")),
    ("repo_name", "VARCHAR", True, pa.string()),
]


def _arrow(cols: list[tuple[str, str, bool, pa.DataType]]) -> pa.Schema:
    return pa.schema([pa.field(n, t, nullable=nullable) for n, _, nullable, t in cols])


def _ddl(table: str, cols: list[tuple[str, str, bool, pa.DataType]]) -> str:
    body = ",\n".join(f"    {n} {d}{'' if nullable else ' NOT NULL'}" for n, d, nullable, _ in cols)
    return f"CREATE TABLE {table} (\n{body}\n)"


EVENTS_SCHEMA = _arrow(_EVENTS_COLUMNS)
PUSH_DAILY_SCHEMA = _arrow(_PUSH_DAILY_COLUMNS)
PUSH_ROWS_SCHEMA = _arrow(_PUSH_ROWS_COLUMNS)

EVENTS_DDL = _ddl("events", _EVENTS_COLUMNS)
PUSH_DAILY_DDL = _ddl("push_daily", _PUSH_DAILY_COLUMNS)

EVENTS_COLUMNS = [c[0] for c in _EVENTS_COLUMNS]
PUSH_DAILY_COLUMNS = [c[0] for c in _PUSH_DAILY_COLUMNS]
SPINE_COLUMNS = [
    "event_id",
    "event_type",
    "created_at",
    "repo_id",
    "repo_name",
    "actor_id",
    "actor_login",
    "org_id",
]
