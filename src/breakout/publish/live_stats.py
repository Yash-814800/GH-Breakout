"""Display-time facts about leaderboard repositories, fetched from the GitHub API.

GH Archive captures only a small share of WatchEvents after 2025-05-23 (ADR-009), so event counts
badly understate real star totals. For the public site (display only, never a model feature,
CLAUDE.md section 6) the exporter asks GitHub for the current name, language, creation date and
``stargazerCount`` of the repositories it is about to show, and keeps a small history of those
counts so the site can show a real gain over the last days (ADR-009 item 4, ADR-029).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from breakout.config import Config
from breakout.enrich import github_meta as gm
from breakout.enrich import http as H
from breakout.logging import get_logger

log = get_logger(__name__)

SNAPSHOT_KEEP_DAYS = 45
GAIN_WINDOW_DAYS = 7


def fetch_live_info(cfg: Config, repo_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Current GitHub facts per repo id; ids absent from the result could not be checked.

    A repo that GitHub reports as gone or blocked comes back with ``status`` != ``ok``. Without
    ``GH_ENRICH_TOKEN`` (or on an API failure) the result is empty and the caller falls back to
    the stored metadata.
    """
    token = os.environ.get("GH_ENRICH_TOKEN", "")
    if not token or not repo_ids:
        if not token:
            log.warning("GH_ENRICH_TOKEN not set: leaderboard shows stored metadata only")
        return {}
    client = H.make_client(cfg.enrich.repo_url)
    api = H.GitHubApi(token, client=client, max_rps=cfg.enrich.max_rps)
    stats = gm.FetchStats()
    out: dict[int, dict[str, Any]] = {}
    bs = cfg.enrich.graphql_batch_size
    try:
        for i in range(0, len(repo_ids), bs):
            for row in gm.fetch_batch(api, repo_ids[i : i + bs], stats):
                out[int(row["repo_id"])] = row
    except Exception as exc:
        log.warning("Live GitHub lookup failed (%s); using stored metadata", exc)
    finally:
        client.close()
    log.info("Live GitHub lookup: %s", json.dumps(stats.as_dict()))
    return out


# ---- star-count history ------------------------------------------------------------------------


def load_snapshots(path: Path) -> dict[str, dict[str, int]]:
    """``{iso_date: {repo_id: stars}}`` from the history file (empty when absent or unreadable)."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {str(d): {str(k): int(v) for k, v in m.items()} for d, m in raw.items()}


def record_snapshot(
    history: dict[str, dict[str, int]],
    day: date,
    stars: dict[int, int],
    keep_days: int = SNAPSHOT_KEEP_DAYS,
) -> dict[str, dict[str, int]]:
    """Add (or replace) the star counts of ``day`` and drop snapshots older than ``keep_days``."""
    merged = {d: dict(m) for d, m in history.items()}
    merged.setdefault(day.isoformat(), {}).update({str(k): int(v) for k, v in stars.items()})
    cutoff = (day - timedelta(days=keep_days)).isoformat()
    return {d: m for d, m in sorted(merged.items()) if d >= cutoff}


def save_snapshots(path: Path, history: dict[str, dict[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, sort_keys=True, separators=(",", ":")) + "\n")


def star_gain(
    history: dict[str, dict[str, int]],
    repo_id: int,
    day: date,
    window: int = GAIN_WINDOW_DAYS,
) -> tuple[int | None, int | None]:
    """Gain in GitHub stars between the oldest snapshot within ``window`` days and ``day``.

    Returns ``(gain, days_covered)``; ``(None, None)`` when no earlier snapshot of this repo exists.
    """
    key = str(repo_id)
    now = history.get(day.isoformat(), {}).get(key)
    if now is None:
        return None, None
    for back in range(window, 0, -1):
        then = history.get((day - timedelta(days=back)).isoformat(), {}).get(key)
        if then is not None:
            return max(now - then, 0), back
    return None, None


def age_days(created_at: datetime | None, day: date) -> int | None:
    """Whole days between the creation of a repo and ``day`` 00:00 UTC (never negative)."""
    if created_at is None:
        return None
    created = created_at if created_at.tzinfo is None else created_at.astimezone(UTC)
    return max((datetime(day.year, day.month, day.day) - created.replace(tzinfo=None)).days, 0)
