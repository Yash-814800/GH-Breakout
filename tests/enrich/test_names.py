from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from breakout.config import load_config
from breakout.enrich import names

HIST = pa.schema(
    [
        ("repo_id", pa.int64()),
        ("repo_name", pa.string()),
        ("first_seen", pa.timestamp("us")),
        ("last_seen", pa.timestamp("us")),
        ("n_events", pa.int64()),
    ]
)


def _history(tmp_path: Path) -> Path:
    d = datetime
    rows = [
        # repo 1 renamed old/name -> new/name on ~2020-06-01
        (1, "old/name", d(2020, 1, 1), d(2020, 5, 31, 23), 10),
        (1, "new/name", d(2020, 6, 1), d(2021, 12, 31), 50),
        # repo 2 took over the name old/name after repo 1 left it
        (2, "old/name", d(2021, 3, 1), d(2021, 9, 1), 5),
        (3, "Some/Repo", d(2019, 1, 1), d(2019, 12, 1), 3),
    ]
    t = pa.Table.from_pylist([dict(zip(HIST.names, r, strict=True)) for r in rows], schema=HIST)
    p = tmp_path / "hist.parquet"
    pq.write_table(t, p)
    return p


def _resolve(tmp_path: Path, pairs):
    hist = _history(tmp_path)
    con = duckdb.connect()
    con.execute("CREATE TABLE q(name VARCHAR, as_of DATE)")
    con.executemany("INSERT INTO q VALUES (?, ?)", pairs)
    return con.execute(
        "SELECT name, repo_id, match_kind FROM ("
        + names.resolve_repo_ids(con, "q", hist).sql_query()
        + ")"
    ).fetchall()


def test_rename_and_name_reuse(tmp_path: Path) -> None:
    out = _resolve(
        tmp_path,
        [
            ("old/name", "2020-03-01"),  # repo 1 under its old name
            ("new/name", "2020-07-01"),  # repo 1 under its new name
            ("old/name", "2021-04-01"),  # name re-used by repo 2
            ("old/name", "2021-12-01"),  # after repo 2 last seen: most recent holder
        ],
    )
    assert [(r[1], r[2]) for r in out] == [
        (1, "interval"),
        (1, "interval"),
        (2, "interval"),
        (2, "before"),
    ]


def test_case_insensitive_and_before_fallback(tmp_path: Path) -> None:
    out = _resolve(tmp_path, [("some/repo", "2019-06-01"), ("SOME/REPO", "2024-01-01")])
    assert [(r[1], r[2]) for r in out] == [(3, "interval"), (3, "before")]


def test_unresolved_and_null_name(tmp_path: Path) -> None:
    out = _resolve(
        tmp_path,
        [("new/name", "2019-01-01"), ("nobody/here", "2020-01-01"), (None, "2020-01-01")],
    )  # new/name was first seen in 2020: it did not exist under that name yet
    assert [(r[1], r[2]) for r in out] == [
        (None, "unresolved"),
        (None, "unresolved"),
        (None, "unresolved"),
    ]


def test_latest_names(tmp_path: Path) -> None:
    con = duckdb.connect()
    names.create_latest_names(con, _history(tmp_path))
    got = dict(con.execute("SELECT repo_id, repo_name FROM latest_names").fetchall())
    assert got == {1: "new/name", 2: "old/name", 3: "Some/Repo"}


def test_build_name_history_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_config
) -> None:
    lake = tmp_path / "lake"
    out = tmp_path / "out"

    def mutate(d: dict) -> None:
        d["lake"]["local_root"] = str(lake)
        d["enrich"]["output_dir"] = str(out)

    cfg = load_config(write_config(mutate))
    for month, rows in {
        "01": [(1, "a/b", datetime(2024, 1, 5)), (1, "a/b", datetime(2024, 1, 9))],
        "02": [(1, "a/c", datetime(2024, 2, 1)), (2, "x/y", datetime(2024, 2, 2))],
    }.items():
        d = lake / "events" / "event_type=WatchEvent" / "year=2024" / f"month={month}"
        d.mkdir(parents=True)
        pq.write_table(
            pa.table(
                {
                    "repo_id": [r[0] for r in rows],
                    "repo_name": [r[1] for r in rows],
                    "created_at": pa.array([r[2] for r in rows], pa.timestamp("us")),
                }
            ),
            d / f"month-2024{month}.parquet",
        )
    first = names.build_name_history(cfg)
    assert first["rows"] == 3 and first["computed"] == 2
    again = names.build_name_history(cfg)
    assert again["computed"] == 0 and again["reused"] == 2 and again["rows"] == 3
    got = duckdb.sql(
        "SELECT repo_id, repo_name, n_events "
        f"FROM read_parquet('{names.history_path(cfg)}') ORDER BY 1,2"
    ).fetchall()
    assert got == [(1, "a/b", 2), (1, "a/c", 1), (2, "x/y", 1)]
