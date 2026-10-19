"""Export ``mart_candidates`` joined with ``mart_labels`` to Parquet for Python (Phase 6).

Candidate and label logic lives only in dbt SQL; this module only reads the marts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from breakout import paths as P
from breakout.config import Config
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

FILE_NAME = "candidates_labels.parquet"
HF_PREFIX = "labels"


def labels_dir() -> Path:
    return P.DERIVED_DIR / "labels"


def labels_path() -> Path:
    return labels_dir() / FILE_NAME


def warehouse_path() -> Path:
    return Path(os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)


EXPORT_SQL = """
select c.repo_id, c.snapshot_date, c.age_days, c.stars_total_before, c.stars_1d, c.stars_7d,
       c.stars_14d, c.stars_prev_7d, c.birth_source, c.repo_name_at_D,
       l.gain_30d, l.threshold_rel, l.breakout_rel, l.breakout_abs, l.days_to_threshold,
       l.first_trending_date, l.trending_covered
from mart_candidates c
join mart_labels l using (repo_id, snapshot_date)
order by c.snapshot_date, c.repo_id
"""


def export_labels(out: Path | None = None, warehouse: Path | None = None) -> dict[str, Any]:
    """Write the joined table (matured snapshots only) and return the summary statistics.

    Idempotent: the file is rewritten with identical content for identical marts.
    """
    out = out or labels_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    con = connect(warehouse or warehouse_path(), read_only=True)
    try:
        con.execute("SET memory_limit='1500MB'")
        con.execute("SET threads=1")
        tmp = out.with_suffix(".tmp")
        con.execute(f"COPY ({EXPORT_SQL}) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)")
        tmp.replace(out)
    finally:
        con.close()
    return summarize(out)


def summarize(path: Path | None = None) -> dict[str, Any]:
    path = path or labels_path()
    con = connect()
    try:
        con.execute("SET threads=1")
        q = f"read_parquet('{path}')"
        total = con.execute(
            f"""select count(*), count(distinct snapshot_date), count(distinct repo_id),
                       count(distinct repo_id) filter (where breakout_rel), avg(breakout_rel::int)
                from {q}"""
        ).fetchone()
        median = con.execute(
            f"""select median(n) from (select count(*) n from {q} group by snapshot_date)"""
        ).fetchone()
        years = con.execute(
            f"""select year(snapshot_date) y, count(distinct snapshot_date), count(*),
                       sum(breakout_rel::int), avg(breakout_rel::int), sum(breakout_abs::int)
                from {q} group by y order by y"""
        ).fetchall()
    finally:
        con.close()
    assert total is not None and median is not None
    return {
        "rows": total[0],
        "snapshots": total[1],
        "distinct_repos": total[2],
        "distinct_positive_repos": total[3],
        "positive_rate": total[4],
        "median_candidates_per_snapshot": median[0],
        "per_year": [
            {
                "year": y,
                "snapshots": s,
                "rows": n,
                "positives": int(p),
                "positive_rate": r,
                "positives_abs": int(a),
            }
            for y, s, n, p, r, a in years
        ],
    }


def load_labels(path: Path | None = None) -> pd.DataFrame:
    """The exported table as a DataFrame (a few million narrow rows)."""
    return pd.read_parquet(path or labels_path())


def upload_labels(cfg: Config, api: Any | None = None) -> dict[str, Any]:
    """Upload the export to the derived repo under ``labels/`` (skipped when unchanged)."""
    from breakout.lake import hf

    api = api or hf.get_api()
    local = labels_path()
    rel = f"{HF_PREFIX}/{FILE_NAME}"
    sha = hf.sha256_file(local)
    remote = {r.path: r for r in hf.remote_list(api, cfg, "derived", HF_PREFIX)}
    r = remote.get(rel)
    if r is not None and r.sha256 == sha:
        return {"uploaded": [], "commits": 0}
    if r is not None and r.sha256 is None and r.blob_id == hf.git_blob_sha1(local):
        return {"uploaded": [], "commits": 0}
    item = hf.UploadItem(local=local, path_in_repo=rel, sha256=sha)
    commits = hf.upload_files(api, cfg, "derived", [item], "labels: update candidates and labels")
    return {"uploaded": [rel], "commits": len(commits)}
