from __future__ import annotations

import duckdb

from breakout import schema
from breakout.ingest.audit import HourAudit, event_paths, render_markdown


def test_ddl_matches_arrow_schema() -> None:
    con = duckdb.connect()
    con.execute(schema.EVENTS_DDL)
    con.execute(schema.PUSH_DAILY_DDL)
    cols = [r[0] for r in con.execute("DESCRIBE events").fetchall()]
    assert cols == schema.EVENTS_SCHEMA.names == schema.EVENTS_COLUMNS
    assert [r[0] for r in con.execute("DESCRIBE push_daily").fetchall()] == (
        schema.PUSH_DAILY_SCHEMA.names
    )
    types = {r[0]: r[1] for r in con.execute("DESCRIBE events").fetchall()}
    assert types["created_at"] == "TIMESTAMP"
    assert types["detail_level"] == "UTINYINT"
    assert schema.SCHEMA_VERSION == 1 and schema.PARSER_VERSION >= 1


def test_event_paths_depth_and_nulls() -> None:
    ev = {"payload": {"a": {"b": {"c": {"d": 1}}, "n": None}, "x": [1, 2]}}
    assert event_paths(ev) == {"payload.a", "payload.a.b", "payload.a.b.c", "payload.x"}


def test_render_flags_fields_dropped_after_trim() -> None:
    def audit(day: str, has_merged: bool) -> HourAudit:
        a = HourAudit(day, 12, lines=10)
        a.type_counts["PullRequestEvent"] = 10
        a.path_counts["PullRequestEvent"]["payload.action"] = 10
        if has_merged:
            a.path_counts["PullRequestEvent"]["payload.pull_request.merged"] = 10
        return a

    md = render_markdown(
        [audit("2024-06-03", True), audit("2025-09-01", True), audit("2025-11-03", False)],
        ["PullRequestEvent"],
        generated=__import__("datetime").date(2026, 1, 1),
    )
    assert "`payload.pull_request.merged` ⚠" in md
    assert "`payload.action` ⚠" not in md
