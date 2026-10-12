from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from breakout.ingest.bq.parity import compare_files
from breakout.schema import EVENTS_COLUMNS, EVENTS_SCHEMA

DAY = date(2024, 6, 3)


def _write(path: Path, rows: list[tuple]) -> Path:
    """Full slim-schema file (all other columns NULL) from (id, created_at, repo_id, action)."""
    con = duckdb.connect()
    con.execute(
        "create table t(event_id bigint, created_at timestamp, repo_id bigint, action varchar)"
    )
    con.executemany("insert into t values (?,?,?,?)", rows)
    extra = [c for c in EVENTS_COLUMNS if c not in ("event_id", "created_at", "repo_id", "action")]
    types = {f.name: str(f.type) for f in EVENTS_SCHEMA}
    duck = {"timestamp[us]": "TIMESTAMP", "bool": "BOOLEAN", "uint8": "UTINYINT"}
    default = "VARCHAR" if "string" in types.values() else "BIGINT"

    def duck_type(c: str) -> str:
        return duck.get(types[c], "VARCHAR" if types[c] == "string" else default)

    nulls = ", ".join(f"CAST(NULL AS {duck_type(c)}) AS {c}" for c in extra)
    con.execute(f"copy (select *, {nulls} from t) to '{path}' (format parquet)")
    return path


def test_identical_files_pass(tmp_path: Path) -> None:
    rows = [(1, "2024-06-03 01:00:00.123", 5, "started"), (2, "2024-06-03 02:00:00", 6, "started")]
    h, b = _write(tmp_path / "h.parquet", rows), _write(tmp_path / "b.parquet", rows)
    r = compare_files({"WatchEvent": h}, {"WatchEvent": b}, DAY, compare_detail=True)
    assert r["ok"] and r["types"]["WatchEvent"]["shared"] == 2


def test_column_mismatch_and_missing_ids_fail(tmp_path: Path) -> None:
    h = _write(tmp_path / "h.parquet", [(1, "2024-06-03 01:00:00", 5, "started")])
    b = _write(
        tmp_path / "b.parquet",
        [(1, "2024-06-03 01:00:00", 5, "opened"), (3, "2024-06-03 03:00:00", 5, None)],
    )
    r = compare_files({"WatchEvent": h}, {"WatchEvent": b}, DAY, compare_detail=True)
    t = r["types"]["WatchEvent"]
    assert not r["ok"] and t["column_mismatches"] == {"action": 1} and t["only_bq"] == 1
    # spine mode ignores detail columns
    r2 = compare_files({"WatchEvent": h}, {"WatchEvent": b}, DAY, compare_detail=False)
    assert r2["types"]["WatchEvent"].get("column_mismatches") == {}
