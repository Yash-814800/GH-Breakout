"""DuckDB connection helper with sensible pragmas."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from breakout.paths import TMP_DIR, ensure_dir

_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "hf://")


def is_remote(path: str | Path) -> bool:
    return str(path).startswith(_REMOTE_PREFIXES)


def total_memory_bytes() -> int:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def ensure_httpfs(con: duckdb.DuckDBPyConnection, *paths: str | Path) -> None:
    """Install/load httpfs only when at least one of ``paths`` is remote."""
    if any(is_remote(p) for p in paths):
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection (in-memory when ``path`` is None) with project pragmas."""
    database = ":memory:" if path is None else str(path)
    if path is not None and not read_only:
        ensure_dir(Path(path).parent)
    con = duckdb.connect(database, read_only=read_only and path is not None)
    memory_mb = max(int(total_memory_bytes() * 0.7 / 1024**2), 256)
    tmp = ensure_dir(TMP_DIR)
    con.execute(f"SET threads TO {os.cpu_count() or 1}")
    con.execute(f"SET memory_limit = '{memory_mb}MB'")
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"SET temp_directory = '{tmp.as_posix()}'")
    return con
