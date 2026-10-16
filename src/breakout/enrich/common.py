"""Helpers shared by the enrichment modules: bounded DuckDB connections, output paths, atomic
parquet writes."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from breakout.config import Config
from breakout.lake import layout
from breakout.paths import ROOT, ensure_dir

MEMORY_LIMIT = "1500MB"


def enrich_dir(cfg: Config) -> Path:
    p = Path(cfg.enrich.output_dir)
    return p if p.is_absolute() else ROOT / p


def staging_dir(cfg: Config, name: str) -> Path:
    return ensure_dir(layout.staging_dir(cfg) / "enrich" / name)


def connect_limited(temp_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Fresh in-memory connection with the CLAUDE.md section 10 limits (1500 MB, 1 thread)."""
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET TimeZone='UTC'")
    if temp_dir is not None:
        ensure_dir(temp_dir)
        con.execute(f"SET temp_directory='{temp_dir.as_posix()}'")
    return con


def sql_str(value: str | Path) -> str:
    """Single-quoted SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def sql_file_list(paths: list[Path]) -> str:
    return "[" + ", ".join(sql_str(p) for p in paths) + "]"


def atomic_copy_parquet(
    con: duckdb.DuckDBPyConnection, select_sql: str, dest: Path, *, order_by: str | None = None
) -> int:
    """``COPY (select) TO dest`` via a temp file + rename. Returns the row count written."""
    ensure_dir(dest.parent)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    q = f"SELECT * FROM ({select_sql})" + (f" ORDER BY {order_by}" if order_by else "")
    con.execute(f"COPY ({q}) TO {sql_str(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = int(con.execute(f"SELECT count(*) FROM read_parquet({sql_str(tmp)})").fetchone()[0])  # type: ignore[index]
    os.replace(tmp, dest)
    return n
