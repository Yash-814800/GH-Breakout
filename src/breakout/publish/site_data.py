"""Publish site data for the frontend (Phase 9 minimal export, Phase 10 full website).

Exports:
- `site/public/data/leaderboard.json`
- `site/public/data/status.json`
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from breakout import paths as P
from breakout.config import Config, get_config
from breakout.logging import get_logger

log = get_logger(__name__)

SITE_DIR = P.ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "public" / "data"
LEADERBOARD_JSON = SITE_DATA_DIR / "leaderboard.json"
STATUS_JSON = SITE_DATA_DIR / "status.json"


def find_latest_predictions(d: date | None = None) -> tuple[Path, date]:
    """Find the predictions parquet file for ``d`` (or newest available)."""
    if d is not None:
        p1 = P.DATA_DIR / "run" / f"predictions_{d.isoformat()}.parquet"
        if p1.exists():
            return p1, d
        p2 = (
            P.DATA_DIR
            / "snapshots"
            / "predictions"
            / f"date={d.isoformat()}"
            / "predictions.parquet"
        )
        if p2.exists():
            return p2, d
        raise FileNotFoundError(f"No predictions file found for {d}")

    # Search run dir
    run_files = sorted(P.DATA_DIR.glob("run/predictions_*.parquet"))
    if run_files:
        latest = run_files[-1]
        d_str = latest.stem.replace("predictions_", "")
        return latest, date.fromisoformat(d_str)

    # Search snapshots dir
    snap_files = sorted(P.DATA_DIR.glob("snapshots/predictions/date=*/predictions.parquet"))
    if snap_files:
        latest = snap_files[-1]
        d_str = latest.parent.name.split("=")[-1]
        return latest, date.fromisoformat(d_str)

    raise FileNotFoundError("No predictions files found in data/run or data/snapshots")


def publish_site_data(
    cfg: Config | None = None,
    d: date | None = None,
    pred_path: Path | None = None,
) -> tuple[Path, Path]:
    """Write leaderboard.json and status.json to site/public/data/."""
    cfg = cfg or get_config(None)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if pred_path is not None:
        target_path = pred_path
        snap_date = d or datetime.now(UTC).date()
    else:
        target_path, snap_date = find_latest_predictions(d)
    log.info("Publishing site data from %s (snapshot date %s)", target_path, snap_date)

    con = duckdb.connect()
    try:
        limit = cfg.site.leaderboard_size
        cols = [
            "snapshot_date",
            "repo_id",
            "repo_name",
            "rank",
            "prob",
            "raw_score",
            "b1_rank",
            "explanation",
            "top_contribs",
            "model_version",
        ]
        # Query top rows
        avail = [
            r[0]
            for r in con.execute(f"describe select * from read_parquet('{target_path}')").fetchall()
        ]
        sel = ", ".join(c for c in cols if c in avail)
        rows = con.execute(
            f"select {sel} from read_parquet('{target_path}') "
            f"order by rank asc, repo_id asc limit {limit}"
        ).fetchall()
        cur_cols = [c for c in cols if c in avail]

        leaderboard_items = []
        for r in rows:
            item = dict(zip(cur_cols, r, strict=True))
            if "snapshot_date" in item and hasattr(item["snapshot_date"], "isoformat"):
                item["snapshot_date"] = item["snapshot_date"].isoformat()
            if "top_contribs" in item and isinstance(item["top_contribs"], str):
                with contextlib.suppress(Exception):
                    item["top_contribs"] = json.loads(item["top_contribs"])
            leaderboard_items.append(item)

        LEADERBOARD_JSON.write_text(json.dumps(leaderboard_items, indent=2, default=str) + "\n")
        log.info("Wrote %d leaderboard items to %s", len(leaderboard_items), LEADERBOARD_JSON)

        # Status JSON
        run_status_path = P.DATA_DIR / "run" / "status.json"
        heartbeat_path = P.ROOT / "status" / "heartbeat.json"

        status_data: dict[str, Any] = {
            "snapshot_date": snap_date.isoformat(),
            "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "n_leaderboard": len(leaderboard_items),
        }

        if run_status_path.exists():
            with contextlib.suppress(Exception):
                status_data["run_status"] = json.loads(run_status_path.read_text())
        elif heartbeat_path.exists():
            with contextlib.suppress(Exception):
                status_data["heartbeat"] = json.loads(heartbeat_path.read_text())

        STATUS_JSON.write_text(json.dumps(status_data, indent=2, default=str) + "\n")
        log.info("Wrote status data to %s", STATUS_JSON)

    finally:
        con.close()

    return LEADERBOARD_JSON, STATUS_JSON
