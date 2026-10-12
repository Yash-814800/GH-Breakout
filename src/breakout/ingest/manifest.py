"""Hourly ingest manifest (Parquet). One row per GH Archive hour.

Status values: ``ok`` (parsed with ``parser_version``), ``missing`` (genuinely absent, stop
retrying), ``pending`` (404 but still inside the late-arrival window), ``error`` (download or
parse failure, retried next run).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

OK, MISSING, PENDING, ERROR = "ok", "missing", "pending", "error"

MANIFEST_SCHEMA = pa.schema(
    [
        pa.field("hour_ts", pa.timestamp("us"), nullable=False),
        pa.field("status", pa.string(), nullable=False),
        pa.field("rows_kept", pa.int64()),
        pa.field("bytes", pa.int64()),
        pa.field("sha256", pa.string()),
        pa.field("attempts", pa.int32()),
        pa.field("last_attempt_at", pa.timestamp("us")),
        pa.field("parser_version", pa.int32()),
        pa.field("source_host", pa.string()),
        pa.field("expected_events", pa.int64()),
        pa.field("expected_sha256", pa.string()),
        pa.field("integrity", pa.string()),
    ]
)

_LOCK = threading.Lock()


@dataclass(frozen=True)
class ManifestRow:
    hour_ts: datetime
    status: str
    rows_kept: int | None = None
    bytes: int | None = None
    sha256: str | None = None
    attempts: int | None = None
    last_attempt_at: datetime | None = None
    parser_version: int | None = None
    source_host: str | None = None
    expected_events: int | None = None
    expected_sha256: str | None = None
    integrity: str | None = None


def iter_hours(start: datetime, end: datetime):
    """Whole hours in ``[start, end)``."""
    t = start
    while t < end:
        yield t
        t += timedelta(hours=1)


def status_for_404(hour_ts: datetime, now: datetime, late_hour_retry_days: int) -> str:
    """404 inside the retry window is ``pending``; after it, ``missing``."""
    age = now - (hour_ts + timedelta(hours=1))
    return PENDING if age <= timedelta(days=late_hour_retry_days) else MISSING


class HourlyManifest:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[datetime, ManifestRow]:
        if not self.path.exists():
            return {}
        table = pq.read_table(self.path)
        known = {f.name for f in MANIFEST_SCHEMA}
        rows = table.to_pylist()  # files written before a column existed simply lack it
        return {
            r["hour_ts"]: ManifestRow(**{k: v for k, v in r.items() if k in known}) for r in rows
        }

    def upsert(self, new_rows: list[ManifestRow]) -> None:
        """Merge rows by ``hour_ts`` and rewrite atomically (thread-safe within a process)."""
        if not new_rows:
            return
        with _LOCK:
            current = self.load()
            for r in new_rows:
                current[r.hour_ts] = r
            ordered = [asdict(current[k]) for k in sorted(current)]
            table = pa.Table.from_pylist(ordered, schema=MANIFEST_SCHEMA)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            pq.write_table(table, tmp, compression="zstd")
            os.replace(tmp, self.path)

    def hours_needing_work(
        self,
        start: datetime,
        end: datetime,
        now: datetime,
        *,
        parser_version: int,
        min_hour_lag: int = 0,
        late_hour_retry_days: int = 3,
        force: bool = False,
        preferred_host: Callable[[datetime], str | None] | None = None,
    ) -> list[datetime]:
        """Hours in ``[start, end)`` that should be (re)ingested at ``now``.

        - hour not yet ended ``min_hour_lag`` hours ago -> not ready, skipped
        - no row, ``error``, or ``ok`` with an older parser version -> work
        - ``pending`` -> work while inside the late-arrival window, afterwards it is treated as
          ``missing`` and skipped
        - ``ok`` from a non-preferred source -> retried while inside the late-arrival window
        - ``missing`` -> skipped unless ``force``
        """
        rows = self.load()
        ready_before = now - timedelta(hours=min_hour_lag)
        out: list[datetime] = []
        for h in iter_hours(start, end):
            if h + timedelta(hours=1) > ready_before:
                continue
            if force:
                out.append(h)
                continue
            row = rows.get(h)
            if row is None or row.status == ERROR:
                out.append(h)
            elif row.status == OK:
                want = preferred_host(h) if preferred_host else None
                if row.parser_version != parser_version:
                    out.append(h)
                elif (
                    want is not None
                    and row.source_host != want
                    and status_for_404(h, now, late_hour_retry_days) == PENDING
                ):
                    # served by a fallback source: look again for the preferred one while the
                    # hour is still inside the late-arrival window
                    out.append(h)
            elif row.status == PENDING and status_for_404(h, now, late_hour_retry_days) == PENDING:
                out.append(h)
            # MISSING: skip
        return out
