"""Dry-run cost survey: bytes per month for spine / full / push queries (dry runs are free)."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from breakout.ingest.bq import sql as Q
from breakout.logging import get_logger

log = get_logger(__name__)


def month_bounds(first: date, last: date) -> list[tuple[str, date, date]]:
    """``(YYYY-MM, start, end)`` per calendar month, clipped to ``[first, last]``."""
    out = []
    y, m = first.year, first.month
    while date(y, m, 1) <= last:
        start = max(date(y, m, 1), first)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        end = min(nxt - timedelta(days=1), last)
        out.append((f"{y:04d}-{m:02d}", start, end))
        y, m = nxt.year, nxt.month
    return out


def list_day_tables(client) -> set[date]:
    """Dates for which a ``githubarchive.day.YYYYMMDD`` table exists (metadata query)."""
    rows = client.query(
        "SELECT table_name FROM `githubarchive.day.INFORMATION_SCHEMA.TABLES`"
    ).result()
    out = set()
    for r in rows:
        name = r["table_name"]
        if len(name) == 8 and name.isdigit():
            out.add(date(int(name[:4]), int(name[4:6]), int(name[6:])))
    return out


def dry_run_bytes(client, sql: str, raw_types: list[str]) -> int:
    from google.cloud import bigquery

    cfg = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        query_parameters=[bigquery.ArrayQueryParameter("raw_types", "STRING", raw_types)],
    )
    return int(client.query(sql, job_config=cfg).total_bytes_processed)


def run_survey(
    first: date,
    last: date,
    raw_types: list[str],
    out_json: Path,
    *,
    project: str | None = None,
    workers: int = 8,
) -> dict:
    from google.cloud import bigquery

    Q.validate_types(raw_types)
    client = bigquery.Client(project=project or os.environ["GCP_PROJECT_ID"])
    existing = list_day_tables(client)
    months = month_bounds(first, last)
    gaps = sorted(
        d
        for _, s, e in months
        for d in (s + timedelta(days=i) for i in range((e - s).days + 1))
        if d not in existing
    )

    def one(item: tuple[str, date, date]) -> tuple[str, dict[str, int]]:
        label, s, e = item
        return label, {
            "spine": dry_run_bytes(client, Q.raw_events_sql(s, e, "spine"), raw_types),
            "full": dry_run_bytes(client, Q.raw_events_sql(s, e, "full"), raw_types),
            "push": dry_run_bytes_plain(client, Q.push_daily_sql(s, e)),
            "spine_no_push": dry_run_bytes(
                client, Q.raw_events_sql(s, e, "spine", include_push=False), raw_types
            ),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(one, months))
    survey = {
        "first": first.isoformat(),
        "last": last.isoformat(),
        "raw_types": raw_types,
        "missing_day_tables": [d.isoformat() for d in gaps],
        "months": results,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(survey, indent=1))
    return survey


def dry_run_bytes_plain(client, sql: str) -> int:
    from google.cloud import bigquery

    cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    return int(client.query(sql, job_config=cfg).total_bytes_processed)
