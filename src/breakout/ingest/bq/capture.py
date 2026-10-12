"""Daily per-type event counts from the public BigQuery GH Archive day tables.

Only the ``type`` column is referenced (``_TABLE_SUFFIX`` supplies the date), so the scan is a
few tens of GB for several years. Always dry-run first and cap ``maximum_bytes_billed``.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from breakout.logging import get_logger

log = get_logger(__name__)

COUNTED_TYPES = {
    "watch": "WatchEvent",
    "fork": "ForkEvent",
    "issues": "IssuesEvent",
    "pr": "PullRequestEvent",
    "push": "PushEvent",
    "creates": "CreateEvent",
}


def daily_counts_sql(start: date, end: date) -> str:
    """Per-day total and per-type counts for ``[start, end]`` (inclusive, 2000-2099 only)."""
    if not (2000 <= start.year <= 2099 and start <= end):
        raise ValueError("bad date range")
    cols = ",\n  ".join(f"COUNTIF(type = '{t}') AS {k}" for k, t in COUNTED_TYPES.items())
    return (
        "SELECT _TABLE_SUFFIX AS d, COUNT(*) AS total,\n  "
        f"{cols}\n"
        "FROM `githubarchive.day.20*`\n"
        f"WHERE _TABLE_SUFFIX BETWEEN '{start:%y%m%d}' AND '{end:%y%m%d}'\n"
        "GROUP BY d ORDER BY d"
    )


def fetch_daily_counts(
    start: date,
    end: date,
    dest: Path,
    *,
    max_bytes: int = 60_000_000_000,
    project: str | None = None,
) -> tuple[int, int]:
    """Dry-run, then run with a hard byte cap; writes parquet. Returns (dry_run, billed) bytes."""
    from google.cloud import bigquery  # local import: only the backfill laptop needs it

    client = bigquery.Client(project=project or os.environ["GCP_PROJECT_ID"])
    sql = daily_counts_sql(start, end)
    dry = client.query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    ).total_bytes_processed
    log.info("capture query dry run: %.1f GB (cap %.1f GB)", dry / 1e9, max_bytes / 1e9)
    if dry > max_bytes:
        raise RuntimeError(f"dry run {dry} bytes exceeds cap {max_bytes}")
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            maximum_bytes_billed=max_bytes, labels={"project": "gh-breakout"}
        ),
    )
    table: pa.Table = job.result().to_arrow()
    table = table.set_column(
        0,
        "day",
        pa.array(
            [
                date(2000 + int(s[:2]), int(s[2:4]), int(s[4:]))
                for s in table.column("d").to_pylist()
            ]
        ),
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dest)
    return dry, int(job.total_bytes_billed or 0)
