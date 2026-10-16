"""Repo name history and name -> repo_id resolution (phase 4.1).

Names are display-only and change over time; this table is the *only* place names are mapped back
to the immutable ``repo_id`` (CLAUDE.md rule 4). Built from the spine columns of WatchEvent files
(every repo that can matter has stars), month by month so peak memory stays bounded; month
aggregates are cached in staging keyed on the input files' names and sizes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb

from breakout.config import Config
from breakout.enrich.common import (
    atomic_copy_parquet,
    connect_limited,
    enrich_dir,
    sql_file_list,
    sql_str,
    staging_dir,
)
from breakout.lake import layout
from breakout.logging import get_logger

log = get_logger(__name__)

NAME_HISTORY = "repo_name_history.parquet"
NAME_SOURCE_TYPE = "WatchEvent"
N_BUCKETS = 32


def history_path(cfg: Config) -> Path:
    return enrich_dir(cfg) / NAME_HISTORY


def _month_of(path: Path) -> str:
    parts = {p.split("=")[0]: p.split("=")[1] for p in path.parts if "=" in p}
    return f"{parts['year']}-{parts['month']}"


def _signature(files: list[Path]) -> str:
    h = hashlib.sha1()
    for f in sorted(files):
        h.update(f"{f.name}:{f.stat().st_size}".encode())
    return h.hexdigest()[:12]


def build_name_history(cfg: Config, *, lake: Path | None = None) -> dict[str, int]:
    """Aggregate ``(repo_id, repo_name, first_seen, last_seen, n_events)`` over the lake.

    Idempotent: month aggregates are reused when the month's files are unchanged, and the final
    file is rewritten atomically with identical content.
    """
    files = layout.glob_for(NAME_SOURCE_TYPE, None, None, cfg)
    if not files:
        raise FileNotFoundError(f"no {NAME_SOURCE_TYPE} files under {layout.lake_root(cfg)}")
    by_month: dict[str, list[Path]] = {}
    for f in files:
        by_month.setdefault(_month_of(f), []).append(f)
    stage = staging_dir(cfg, "names")
    parts: list[Path] = []
    computed = reused = 0
    for month, mfiles in sorted(by_month.items()):
        out = stage / f"{month}-{_signature(mfiles)}.parquet"
        parts.append(out)
        if out.exists():
            reused += 1
            continue
        for stale in stage.glob(f"{month}-*.parquet"):
            stale.unlink()
        con = connect_limited(stage / "tmp")
        try:
            atomic_copy_parquet(
                con,
                f"""SELECT repo_id, repo_name, min(created_at) AS first_seen,
                           max(created_at) AS last_seen, count(*) AS n_events
                    FROM read_parquet({sql_file_list(mfiles)}, hive_partitioning=false)
                    WHERE repo_name IS NOT NULL
                    GROUP BY repo_id, repo_name""",
                out,
            )
        finally:
            con.close()
        computed += 1
        log.info("names: %s done (%d files)", month, len(mfiles))
    # bounded-memory merge: aggregate per repo_id bucket, then one sort-only pass
    buckets: list[Path] = []
    for b in range(N_BUCKETS):
        out = stage / f"bucket-{b:02d}-{_signature(parts)}.parquet"
        buckets.append(out)
        if out.exists():
            continue
        for stale in stage.glob(f"bucket-{b:02d}-*.parquet"):
            stale.unlink()
        con = connect_limited(stage / "tmp")
        try:
            atomic_copy_parquet(
                con,
                f"""SELECT repo_id, repo_name, min(first_seen) AS first_seen,
                           max(last_seen) AS last_seen, sum(n_events)::BIGINT AS n_events
                    FROM read_parquet({sql_file_list(parts)})
                    WHERE repo_id % {N_BUCKETS} = {b}
                    GROUP BY repo_id, repo_name""",
                out,
            )
        finally:
            con.close()
        log.info("names: merge bucket %d/%d", b + 1, N_BUCKETS)
    con = connect_limited(stage / "tmp")
    try:
        n = atomic_copy_parquet(
            con,
            f"SELECT * FROM read_parquet({sql_file_list(buckets)})",
            history_path(cfg),
            order_by="repo_id, first_seen, repo_name",
        )
    finally:
        con.close()
    return {"months": len(by_month), "computed": computed, "reused": reused, "rows": n}


def create_latest_names(con: duckdb.DuckDBPyConnection, history: str | Path) -> None:
    """Create view ``latest_names(repo_id, repo_name)``: the most recent name per repo_id."""
    con.execute(
        f"""CREATE OR REPLACE VIEW latest_names AS
            SELECT repo_id, repo_name FROM (
              SELECT repo_id, repo_name,
                     row_number() OVER (PARTITION BY repo_id
                                        ORDER BY last_seen DESC, first_seen DESC, repo_name) rn
              FROM read_parquet({sql_str(history)})
            ) WHERE rn = 1"""
    )


def resolve_repo_ids(
    con: duckdb.DuckDBPyConnection, names_with_dates: str, history: str | Path
) -> duckdb.DuckDBPyRelation:
    """Resolve ``(name, as_of)`` pairs to a repo_id as known on ``as_of``.

    ``names_with_dates`` is a table/view in ``con`` with columns ``name`` (``owner/repo``) and
    ``as_of`` (DATE or TIMESTAMP); any other columns are passed through. Output adds ``repo_id``
    and ``match_kind``:

    - ``interval``: the name's seen-interval ``[first_seen, last_seen]`` contains ``as_of``
      (ties: latest ``first_seen``, so a name re-used by a newer repo resolves to the newer one);
    - ``before``: no interval contains it; the repo with that name seen most recently before;
    - NULL repo_id / ``unresolved``: never seen with that name on or before ``as_of`` (a repo
      first seen later is *not* matched: it did not exist under that name yet) or NULL name.

    Names match case-insensitively (GitHub names are case-insensitive).
    """
    con.execute(
        "CREATE OR REPLACE TEMP TABLE _hist AS SELECT repo_id, lower(repo_name) AS lname, "
        f"first_seen, last_seen FROM read_parquet({sql_str(history)})"
    )
    return con.sql(
        f"""
        WITH q AS (
          SELECT *, row_number() OVER () AS _qid,
                 lower(name) AS _lname,
                 CAST(as_of AS DATE) AS _day
          FROM {names_with_dates}
        ),
        cand AS (
          SELECT q._qid, h.repo_id,
                 CASE WHEN h.first_seen < q._day + INTERVAL 1 DAY AND h.last_seen >= q._day
                      THEN 0 ELSE 1 END AS kind,
                 h.first_seen, h.last_seen
          FROM q JOIN _hist h ON h.lname = q._lname
          WHERE h.first_seen < q._day + INTERVAL 1 DAY
        ),
        best AS (
          SELECT _qid, repo_id, kind FROM (
            SELECT *, row_number() OVER (
                      PARTITION BY _qid
                      ORDER BY kind, CASE WHEN kind = 0 THEN first_seen ELSE last_seen END DESC,
                               repo_id) rn
            FROM cand) WHERE rn = 1
        )
        SELECT q.* EXCLUDE (_qid, _lname, _day),
               b.repo_id AS repo_id,
               CASE b.kind WHEN 0 THEN 'interval' WHEN 1 THEN 'before'
                    ELSE 'unresolved' END AS match_kind
        FROM q LEFT JOIN best b USING (_qid)
        ORDER BY q._qid
        """
    )


__all__ = ["build_name_history", "create_latest_names", "history_path", "resolve_repo_ids"]
