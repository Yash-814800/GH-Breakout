"""Shared constants/helpers for ingest tests (imported by name; tests/ has no packages)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from breakout.ingest.gharchive import DownloadResult, hour_filename

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ALL_FIXTURES = sorted(FIXTURES.glob("gharchive_*.sample.json.gz"))
RAW_TYPES = [
    "WatchEvent",
    "ForkEvent",
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "ReleaseEvent",
    "CreateEvent",
    "PublicEvent",
]


def fixture_for(day: str) -> Path:
    return FIXTURES / f"gharchive_{day}-12.sample.json.gz"


class FakeDownloader:
    """Serves a fixture for every requested hour (or 404 for hours in ``missing``)."""

    def __init__(self, fixture: Path, missing: set[int] | None = None):
        self.fixture = fixture
        self.missing = missing or set()
        self.calls: list[datetime] = []

    def __call__(self, ts: datetime, dest_dir: Path) -> DownloadResult:
        self.calls.append(ts)
        if ts.hour in self.missing:
            return DownloadResult("missing")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / hour_filename(ts)
        shutil.copy(self.fixture, dest)
        return DownloadResult("ok", dest, "0" * 64, dest.stat().st_size)
