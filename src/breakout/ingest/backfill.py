"""Resumable hourly-file backfill from the cutover date onward (ADR-010).

Order: the trusted era ``[cutover_date, trusted_end]`` first, then the degraded era
``(trusted_end, last complete day]`` (kept and flagged, never trained or evaluated on); plus any
``history.hourly_gap_days`` before the cutover that BigQuery day tables lack. Within an era days go
oldest to newest. Resumability comes from the hourly manifest: hours already ``ok`` at the current
parser version are skipped, so an interrupted run simply continues.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from breakout.config import Config
from breakout.ingest.day import DaySummary, ingest_day
from breakout.logging import get_logger

log = get_logger(__name__)

MAX_CONCURRENT_DOWNLOADS = 4


@dataclass(frozen=True)
class PlannedDay:
    day: date
    era: str  # trusted | degraded | gap


def last_complete_day(cfg: Config, now: datetime | None = None) -> date:
    """Latest day whose 24 hours have all ended at least ``daily.min_hour_lag`` hours ago."""
    now = (now or datetime.now(UTC)).replace(tzinfo=None)
    available_until = now - timedelta(hours=cfg.daily.min_hour_lag)
    # day D is complete once D+1 00:00 <= available_until, i.e. D <= available_until.date() - 1
    return available_until.date() - timedelta(days=1)


def plan_days(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    now: datetime | None = None,
) -> list[PlannedDay]:
    cutover = cfg.history.cutover_date
    if cutover is None:
        raise ValueError("history.cutover_date is not set")
    first = start or cutover
    last = end or last_complete_day(cfg, now)
    days: list[PlannedDay] = []
    for gap in sorted(cfg.history.hourly_gap_days):
        if start is None and (end is None or gap <= end):
            days.append(PlannedDay(gap, "gap"))
    trusted_end = cfg.history.trusted_end
    d = first
    while d <= min(trusted_end, last):
        days.append(PlannedDay(d, "trusted"))
        d += timedelta(days=1)
    d = max(first, trusted_end + timedelta(days=1))
    while d <= last:
        days.append(PlannedDay(d, "degraded"))
        d += timedelta(days=1)
    return days


def run_hourly_backfill(
    cfg: Config,
    days: list[PlannedDay],
    *,
    workers: int = 2,
    keep_raw: bool = False,
    force: bool = False,
    on_day: Callable[[PlannedDay, DaySummary], None] | None = None,
) -> list[DaySummary]:
    """Ingest ``days`` in order with at most ``workers`` (<= 4) concurrent downloads."""
    if not 1 <= workers <= MAX_CONCURRENT_DOWNLOADS:
        raise ValueError(f"workers must be between 1 and {MAX_CONCURRENT_DOWNLOADS}")
    results: list[DaySummary] = []
    # one hour at a time per day, `workers` days in flight -> at most `workers` downloads
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            (
                pd,
                pool.submit(
                    ingest_day, pd.day, cfg=cfg, force=force, keep_raw=keep_raw, hour_workers=1
                ),
            )
            for pd in days
        ]
        for pd, fut in futures:
            summary = fut.result()
            results.append(summary)
            if on_day:
                on_day(pd, summary)
    return results
