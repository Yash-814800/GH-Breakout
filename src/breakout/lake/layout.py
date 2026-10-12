"""Local lake layout, mirrored 1:1 on Hugging Face (Phase 3).

events/event_type={T}/year={YYYY}/month={MM}/bq-{YYYYMM}.parquet        BigQuery history
events/event_type={T}/year={YYYY}/month={MM}/day-{YYYY-MM-DD}.parquet   hourly-sourced days
events/event_type={T}/year={YYYY}/month={MM}/month-{YYYYMM}.parquet     compacted month
push_daily/year={YYYY}/month={MM}/{bq,day,month}-...parquet             same pattern, no type
manifests/hourly_manifest.parquet, manifests/bq_backfill.json
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from breakout.config import Config, get_config
from breakout.paths import ROOT

EVENTS_DIR = "events"
PUSH_DIR = "push_daily"
PUSH_TYPE = "PushEvent"


def lake_root(cfg: Config | None = None) -> Path:
    root = Path((cfg or get_config()).lake.local_root)
    return root if root.is_absolute() else ROOT / root


def data_root(cfg: Config | None = None) -> Path:
    """Parent of the lake: holds ``staging/`` and ``raw/`` next to ``lake/``."""
    return lake_root(cfg).parent


def manifests_dir(cfg: Config | None = None) -> Path:
    return lake_root(cfg) / "manifests"


def hourly_manifest_path(cfg: Config | None = None) -> Path:
    return manifests_dir(cfg) / "hourly_manifest.parquet"


def bq_manifest_path(cfg: Config | None = None) -> Path:
    return manifests_dir(cfg) / "bq_backfill.json"


def staging_dir(cfg: Config | None = None) -> Path:
    return data_root(cfg) / "staging"


def raw_dir(cfg: Config | None = None) -> Path:
    return data_root(cfg) / "raw"


def month_dir(event_type: str, year: int, month: int, cfg: Config | None = None) -> Path:
    base = lake_root(cfg)
    ym = f"year={year:04d}/month={month:02d}"
    if event_type == PUSH_TYPE:
        return base / PUSH_DIR / ym
    return base / EVENTS_DIR / f"event_type={event_type}" / ym


def day_file(event_type: str, day: date, cfg: Config | None = None) -> Path:
    return month_dir(event_type, day.year, day.month, cfg) / f"day-{day.isoformat()}.parquet"


def bq_file(event_type: str, year: int, month: int, cfg: Config | None = None) -> Path:
    return month_dir(event_type, year, month, cfg) / f"bq-{year:04d}{month:02d}.parquet"


def month_file(event_type: str, year: int, month: int, cfg: Config | None = None) -> Path:
    return month_dir(event_type, year, month, cfg) / f"month-{year:04d}{month:02d}.parquet"


def _type_root(event_type: str, cfg: Config | None) -> Path:
    base = lake_root(cfg)
    if event_type == PUSH_TYPE:
        return base / PUSH_DIR
    return base / EVENTS_DIR / f"event_type={event_type}"


def glob_for(
    event_type: str,
    start: date | None = None,
    end: date | None = None,
    cfg: Config | None = None,
) -> list[Path]:
    """Existing files for ``event_type`` overlapping ``[start, end]`` (inclusive, either open).

    Month granularity for ``bq-``/``month-`` files, day granularity for ``day-`` files. Within a
    month a compacted ``month-`` file supersedes the ``bq-`` and ``day-`` files it replaced.
    """
    root = _type_root(event_type, cfg)
    if not root.exists():
        return []
    out: list[Path] = []
    for mdir in sorted(root.glob("year=*/month=*")):
        year = int(mdir.parent.name.split("=")[1])
        month = int(mdir.name.split("=")[1])
        first = date(year, month, 1)
        last = date(year + (month == 12), month % 12 + 1, 1)  # exclusive
        if end is not None and first > end:
            continue
        if start is not None and last <= start:
            continue
        compacted = sorted(mdir.glob("month-*.parquet"))
        if compacted:
            out.extend(compacted)
            continue
        out.extend(sorted(mdir.glob("bq-*.parquet")))
        for f in sorted(mdir.glob("day-*.parquet")):
            d = date.fromisoformat(f.stem.removeprefix("day-"))
            if (start is None or d >= start) and (end is None or d <= end):
                out.append(f)
    return out
