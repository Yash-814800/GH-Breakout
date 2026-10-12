from __future__ import annotations

import gzip
from datetime import datetime
from pathlib import Path

import pytest
from ingest_helpers import ALL_FIXTURES, RAW_TYPES, fixture_for

from breakout.ingest.parse import parse_hour_file
from breakout.schema import EVENTS_COLUMNS, EVENTS_SCHEMA, PUSH_ROWS_SCHEMA


def _day(path: Path) -> str:
    return path.name.split("_")[1][:10]


def _parse(path: Path, day: str | None = None, **kw):
    ts = datetime.fromisoformat((day or _day(path)) + "T12:00:00")
    return parse_hour_file(path, ts, raw_types=RAW_TYPES, **kw)


def test_fixtures_exist_and_are_small() -> None:
    assert len(ALL_FIXTURES) == 9
    for f in ALL_FIXTURES:
        assert f.stat().st_size < 2_000_000, f


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=_day)
def test_parser_on_every_fixture(path: Path) -> None:
    r = _parse(path)
    t = r.events
    assert t.schema == EVENTS_SCHEMA
    assert r.push_rows.schema == PUSH_ROWS_SCHEMA
    assert t.num_rows > 0 and r.push_rows.num_rows > 0
    assert t.column_names == EVENTS_COLUMNS
    for col in ("event_id", "event_type", "created_at", "repo_id", "actor_id", "source"):
        assert t.column(col).null_count == 0, col
    assert set(t.column("detail_level").to_pylist()) == {1}
    assert set(t.column("source").to_pylist()) == {"hourly"}
    assert set(t.column("event_type").to_pylist()) <= set(RAW_TYPES)
    ids = t.column("event_id").to_pylist()
    assert len(ids) == len(set(ids))
    assert r.stats.bad_json_lines == 0
    assert r.stats.lines_read >= t.num_rows + r.push_rows.num_rows


@pytest.mark.parametrize("path", ALL_FIXTURES, ids=_day)
def test_watch_event_action_started(path: Path) -> None:
    rows = _parse(path).events.to_pylist()
    watch = [r for r in rows if r["event_type"] == "WatchEvent"]
    assert watch
    assert {r["action"] for r in watch} == {"started"}


def test_issue_comment_on_pull_request_flagged() -> None:
    for day in ("2018-06-01", "2024-06-03", "2025-11-03"):
        rows = _parse(fixture_for(day)).events.to_pylist()
        comments = [r for r in rows if r["event_type"] == "IssueCommentEvent"]
        assert any(r["is_pull_request"] is True for r in comments), day
        assert any(r["is_pull_request"] is False for r in comments), day


def test_detail_columns_populated_pre_trim() -> None:
    rows = _parse(fixture_for("2024-06-03")).events.to_pylist()
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["event_type"], []).append(r)
    assert all(r["target_user_id"] and r["target_created_at"] for r in by_type["PullRequestEvent"])
    assert any(r["pr_merged"] is True for r in by_type["PullRequestEvent"])
    assert all(r["forkee_repo_id"] for r in by_type["ForkEvent"])
    assert all(r["ref_type"] for r in by_type["CreateEvent"])
    assert all(r["review_state"] for r in by_type["PullRequestReviewEvent"])
    assert all(r["release_prerelease"] is not None for r in by_type["ReleaseEvent"])
    assert all(r["number"] for r in by_type["IssuesEvent"])


def test_post_trim_missing_fields_are_null_not_errors() -> None:
    rows = _parse(fixture_for("2025-11-03")).events.to_pylist()
    prs = [r for r in rows if r["event_type"] == "PullRequestEvent"]
    assert prs
    for r in prs:
        assert r["number"] is not None  # payload.number survives the trim
        assert r["is_pull_request"] is True
        assert r["target_user_id"] is None
        assert r["target_created_at"] is None
        assert r["pr_merged"] is None


def test_timestamps_are_naive_utc() -> None:
    r = _parse(fixture_for("2024-06-03"))
    created = r.events.column("created_at").to_pylist()
    assert all(c.tzinfo is None for c in created)
    assert all(c.date().isoformat() == "2024-06-03" for c in created)
    assert {c.hour for c in created} <= {11, 12, 13}


def test_duplicate_line_deduped(tmp_path: Path) -> None:
    src = fixture_for("2024-06-03")
    with gzip.open(src, "rb") as fh:
        lines = fh.read().splitlines(keepends=True)
    dup = tmp_path / "dup.json.gz"
    with gzip.open(dup, "wb") as out:
        out.writelines(lines)
        out.write(lines[0])
        out.write(lines[-1])
    base = _parse(src)
    r = _parse(dup, day="2024-06-03")
    assert r.stats.duplicates == 2
    assert r.events.num_rows == base.events.num_rows
    assert r.push_rows.num_rows == base.push_rows.num_rows


def test_bad_json_and_bad_ids_counted(tmp_path: Path) -> None:
    p = tmp_path / "bad.json.gz"
    good = (
        b'{"id":"1","type":"WatchEvent","actor":{"id":5,"login":"a"},"repo":{"id":9,"name":"o/r"},'
        b'"payload":{"action":"started"},"created_at":"2024-06-03T12:00:01Z"}\n'
    )
    no_repo = good.replace(b'"repo":{"id":9,"name":"o/r"}', b'"repo":{}').replace(b'"1"', b'"2"')
    bad_id = good.replace(b'"id":"1"', b'"id":"abc"')
    with gzip.open(p, "wb") as out:
        out.write(good + b"{not json\n" + no_repo + bad_id)
    r = parse_hour_file(p, datetime(2024, 6, 3, 12), raw_types=RAW_TYPES)
    assert r.events.num_rows == 1
    assert r.stats.bad_json_lines == 1
    assert r.stats.bad_ids == 2
    assert r.events.to_pylist()[0]["org_id"] is None
