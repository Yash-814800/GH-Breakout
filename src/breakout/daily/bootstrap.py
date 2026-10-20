"""Make a clean runner look like the dev machine before the daily steps run (Phase 9).

A GitHub Actions runner starts empty. Before planning and building features it needs: the hourly
manifest (merged from the per-month fragments on the events repo), the event files of the working
window, the enrichment tables, the persistent state, the champion model and the dbt packages.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from breakout import paths as P
from breakout.config import Config
from breakout.dbt_runner import run_dbt
from breakout.features import state as state_mod
from breakout.ingest.manifest import HourlyManifest, ManifestRow
from breakout.lake import hf, layout, sync
from breakout.logging import get_logger
from breakout.ml import registry as reg_mod

log = get_logger(__name__)

FRAGMENT_PREFIX = "manifests/hourly"
ENRICH_FILES = (
    "repo_metadata",
    "repo_name_history",
    "actor_id_age_map",
    "trending",
    "hn_stories",
)


def merge_manifest_fragments(cfg: Config, fragments: list[Path]) -> int:
    """Upsert every row of the fragment files into the local hourly manifest; returns rows read."""
    from breakout.ingest.manifest import MANIFEST_SCHEMA

    known = {f.name for f in MANIFEST_SCHEMA}
    rows: list[ManifestRow] = []
    for f in sorted(fragments):
        rows += [
            ManifestRow(**{k: v for k, v in r.items() if k in known})
            for r in pq.read_table(f).to_pylist()
        ]
    HourlyManifest(layout.hourly_manifest_path(cfg)).upsert(rows)
    return len(rows)


def pull_manifest(cfg: Config) -> int:
    api = hf.get_api()
    remote = [f.path for f in hf.remote_list(api, cfg, sync.KEY, FRAGMENT_PREFIX)]
    root = layout.lake_root(cfg)
    got = hf.download_files(api, cfg, sync.KEY, remote, root)
    return merge_manifest_fragments(cfg, got)


def pull_window(cfg: Config, target_date: date) -> int:
    """Event files covering the dbt window ``[target - recent_window_days, target)``."""
    start = target_date - timedelta(days=cfg.daily.recent_window_days)
    got = sync.pull(
        hf.get_api(),
        cfg,
        types=list(cfg.events.raw_types),
        start=start,
        end=target_date - timedelta(days=1),
        push_daily=True,
    )
    return len(got)


def pull_enrich(cfg: Config) -> int:
    paths = [f"{cfg.enrich.hf_prefix}/{n}.parquet" for n in ENRICH_FILES]
    got = hf.download_files(hf.get_api(), cfg, "derived", paths, P.DERIVED_DIR)
    return len(got)


def pull_prefix(cfg: Config, prefix: str) -> int:
    """Download every file under ``prefix`` of the derived repo into the local derived dir."""
    api = hf.get_api()
    paths = [f.path for f in hf.remote_list(api, cfg, "derived", prefix)]
    return len(hf.download_files(api, cfg, "derived", paths, P.DERIVED_DIR))


def bootstrap_weekly(cfg: Config) -> dict[str, Any]:
    """Inputs of the weekly retrain: training rows, labels, live features and the registry."""
    out = {p: pull_prefix(cfg, p) for p in ("training", "labels", "live")}
    reg_mod.load_champion(cfg, pull=True)
    log.info("Weekly bootstrap done: %s", out)
    return out


def bootstrap(cfg: Config, target_date: date) -> dict[str, Any]:
    """Pull what a fresh runner lacks. Idempotent: present, verified files are not refetched."""
    out: dict[str, Any] = {}
    for d in (P.ROOT / "ledger", P.ROOT / "status", P.DATA_DIR / "run"):
        d.mkdir(parents=True, exist_ok=True)
    if not (P.ROOT / "dbt" / "dbt_packages").exists() and (rc := run_dbt(cfg, ["deps"])) != 0:
        raise RuntimeError(f"dbt deps failed with code {rc}")
    out["manifest_rows"] = pull_manifest(cfg)
    out["window_files"] = pull_window(cfg, target_date)
    out["enrich_files"] = pull_enrich(cfg)
    out["live_files"] = pull_prefix(cfg, "live")
    if not state_mod.TASTEMAKER_STATE_PATH.exists():
        state_mod.pull_state(cfg)
    reg_mod.load_champion(cfg, pull=True)
    log.info("Bootstrap done: %s", out)
    return out
