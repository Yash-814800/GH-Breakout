"""Build, export and verify the feature marts (Phase 7)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from breakout import dbt_runner as R
from breakout import features_dict as fd
from breakout import paths as P
from breakout.config import Config
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

GROUP_MODELS = [
    "feat_star_dynamics",
    "feat_activity",
    "feat_stargazers",
    "feat_tastemaker",
    "feat_owner",
    "feat_detail",
    "feat_enrich",
]
MART = "mart_repo_features"
SINGULAR_TESTS = R.FEATURE_SINGULAR_TESTS
TASTEMAKER_BUCKETED = ["int_actor_early_stars", "int_actor_early_cum"]
TASTEMAKER_SMALL = ["int_repo_first_hit", "int_tastemaker_thresholds"]
LABEL_COLUMNS = [
    "gain_30d",
    "threshold_rel",
    "breakout_rel",
    "breakout_abs",
    "days_to_threshold",
    "first_trending_date",
    "trending_covered",
]
TRAINING_DIR = P.DERIVED_DIR / "training"
FEATURES_LABELS_DIR = TRAINING_DIR / "features_labels"
MANIFEST_PATH = TRAINING_DIR / "feature_manifest.json"
LIVE_DIR = P.DERIVED_DIR / "live"
HF_PREFIX = "training"


def warehouse_path() -> Path:
    return Path(os.environ.get("GHB_WAREHOUSE") or P.WAREHOUSE)


def drop_feature_tables(warehouse: Path | None = None) -> None:
    """Drop the feature models (for a --full-refresh build after a schema change)."""
    con = duckdb.connect(str(warehouse or warehouse_path()))
    try:
        for t in [*TASTEMAKER_BUCKETED, *TASTEMAKER_SMALL, *GROUP_MODELS, MART]:
            con.execute(f"drop table if exists {t}")
    finally:
        con.close()


def run_features(
    cfg: Config,
    *,
    n_buckets: int = 32,
    test: bool = True,
    full_refresh: bool = False,
) -> int:
    """Weekly-history build of all feature models over the trusted history (resumable by bucket).

    1. the tastemaker intermediates (bucketed by repo / actor, ADR-020 style), thresholds, first hits;
    2. the top-languages seed;
    3. per repo_id bucket: every feat_* group and mart_repo_features (one dbt call per bucket);
    4. dbt tests of the new models.
    Candidates (mart_candidates) must exist for the history already (``breakout build labels``).
    """
    hv = R.history_vars(cfg, n_buckets=n_buckets)
    if full_refresh:
        drop_feature_tables()
    if (rc := R.run_dbt(cfg, ["seed", "--select", "top_languages"])) != 0:
        return rc
    if (rc := R.run_bucketed(cfg, TASTEMAKER_BUCKETED, extra_vars=hv)) != 0:
        return rc
    if (rc := R.run_dbt(cfg, ["run", "--select", *TASTEMAKER_SMALL], extra_vars=hv)) != 0:
        return rc
    done = R._done_buckets(MART)
    for b in range(n_buckets):
        if b in done:
            continue
        log.info("features bucket %d/%d", b + 1, n_buckets)
        rc = R.run_dbt(
            cfg,
            ["run", "--select", *GROUP_MODELS, MART],
            extra_vars={**hv, "bucket": b},
        )
        if rc != 0:
            return rc
    if test:
        rc = R.run_dbt(
            cfg,
            [
                "test",
                "--select",
                *TASTEMAKER_BUCKETED,
                *TASTEMAKER_SMALL,
                *GROUP_MODELS,
                MART,
                *SINGULAR_TESTS,
            ],
            extra_vars=hv,
        )
    for uid, secs in sorted(R.TIMINGS.items(), key=lambda kv: -kv[1])[:20]:
        log.info("%-60s %9.1fs", uid, secs)
    return rc if test else 0


def run_features_single(cfg: Config, d: date, *, window: tuple[date, date] | None = None) -> int:
    """Live build for one snapshot date: candidates, tastemaker tables and all features for ``d``.

    Same SQL as the history build with ``snapshot_dates_mode = single``. The warehouse must already hold
    the staging / intermediate tables of the daily window (Phase 9 builds them).
    """
    ev: dict[str, Any] = {
        "snapshot_dates_mode": "single",
        "snapshot_date": d.isoformat(),
        "n_buckets": 1,
    }
    if window:
        ev["events_start"], ev["events_end"] = window[0].isoformat(), window[1].isoformat()
    for args in (
        ["seed", "--select", "top_languages"],
        ["run", "--select", "mart_snapshot_dates", "mart_candidates"],
        ["run", "--select", *TASTEMAKER_BUCKETED, *TASTEMAKER_SMALL, *GROUP_MODELS, MART],
    ):
        if (rc := R.run_dbt(cfg, args, extra_vars=ev)) != 0:
            return rc
    return 0


def _git_sha() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=P.ROOT, text=True).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "dbt", "config"], cwd=P.ROOT, text=True
        )
        return sha + ("-dirty" if dirty.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def mart_columns(warehouse: Path | None = None) -> list[tuple[str, str]]:
    con = duckdb.connect(str(warehouse or warehouse_path()), read_only=True)
    try:
        return con.execute(
            """select column_name, data_type from information_schema.columns
               where table_name = 'mart_repo_features' order by ordinal_position"""
        ).fetchall()
    finally:
        con.close()


def export_training(cfg: Config, warehouse: Path | None = None) -> dict[str, Any]:
    """Export mart_repo_features joined with the labels of matured snapshots, one file per year.

    Output: ``training/features_labels/year=YYYY/part-0.parquet`` and ``training/feature_manifest.json``.
    The first columns are exactly the mart's columns (same order and types as the live file), then the label
    columns. Idempotent: files are rewritten with identical content for identical marts.
    """
    wh = warehouse or warehouse_path()
    cols = [c for c, _ in mart_columns(wh)]
    missing, extra = fd.compare_with_columns(fd.load(), cols)
    if missing or extra:
        raise RuntimeError(f"dictionary and mart differ: undocumented {missing}, unused {extra}")
    sel = ", ".join(f"f.{c}" for c in cols)
    lab = ", ".join(f"l.{c}" for c in LABEL_COLUMNS)
    FEATURES_LABELS_DIR.mkdir(parents=True, exist_ok=True)
    con = connect(wh, read_only=True)
    try:
        con.execute("SET memory_limit='1500MB'")
        con.execute("SET threads=1")
        years = [
            r[0]
            for r in con.execute(
                f"""select distinct year(f.snapshot_date) from {MART} f
                join mart_labels l using (repo_id, snapshot_date) order by 1"""
            ).fetchall()
        ]
        counts: dict[int, int] = {}
        for y in years:
            out = FEATURES_LABELS_DIR / f"year={y}" / "part-0.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            con.execute(
                f"""copy (select {sel}, {lab} from {MART} f join mart_labels l using (repo_id, snapshot_date)
                          where year(f.snapshot_date) = {y} order by f.snapshot_date, f.repo_id)
                    to '{tmp}' (format parquet, compression zstd)"""
            )
            tmp.replace(out)
            counts[y] = con.execute(f"select count(*) from read_parquet('{out}')").fetchone()[0]  # type: ignore[index]
    finally:
        con.close()
    feats = fd.load()
    manifest = {
        "features": [c for c in cols if c not in fd.MART_KEY_COLUMNS],
        "live_features": fd.live_features(feats),
        "label_columns": LABEL_COLUMNS,
        "dictionary_sha256": fd.dictionary_hash(),
        "dbt_git_sha": _git_sha(),
        "rows_per_year": {str(y): n for y, n in counts.items()},
        "rows_total": sum(counts.values()),
        "columns": {c: t for c, t in mart_columns(wh)},
    }
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def export_live(d: date, warehouse: Path | None = None) -> Path:
    """Write the single-date features of ``d`` to ``live/features_D.parquet`` (mart columns only)."""
    wh = warehouse or warehouse_path()
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    out = LIVE_DIR / f"features_{d.isoformat()}.parquet"
    con = connect(wh, read_only=True)
    try:
        con.execute("SET memory_limit='1500MB'")
        con.execute("SET threads=1")
        tmp = out.with_suffix(".tmp")
        con.execute(
            f"""copy (select * from {MART} where snapshot_date = date '{d}' order by repo_id)
                to '{tmp}' (format parquet, compression zstd)"""
        )
        tmp.replace(out)
    finally:
        con.close()
    return out


def parquet_schema(path: Path) -> list[tuple[str, str]]:
    con = duckdb.connect()
    try:
        return [
            (r[0], r[1])
            for r in con.execute(f"describe select * from read_parquet('{path}')").fetchall()
        ]
    finally:
        con.close()


def schemas_match(live: Path, training_dir: Path | None = None) -> tuple[bool, str]:
    """Live file columns / types equal the mart columns at the head of the training table."""
    train_files = sorted((training_dir or FEATURES_LABELS_DIR).glob("year=*/part-0.parquet"))
    if not train_files:
        return False, "no training files"
    train = parquet_schema(train_files[-1])
    live_s = parquet_schema(live)
    head = train[: len(live_s)]
    if head != live_s:
        diff = [(a, b) for a, b in zip(head, live_s, strict=False) if a != b]
        return False, f"live {len(live_s)} columns vs training head {len(head)}: {diff[:5]}"
    return True, f"{len(live_s)} columns identical (names, order, types)"


def null_rates(warehouse: Path | None = None) -> dict[str, dict[str, float]]:
    """NULL share of every feature, overall and per year of snapshot_date."""
    wh = warehouse or warehouse_path()
    cols = [c for c, _ in mart_columns(wh) if c not in fd.MART_KEY_COLUMNS]
    con = connect(wh, read_only=True)
    try:
        con.execute("SET memory_limit='1500MB'")
        con.execute("SET threads=1")
        agg = ", ".join(f"avg(({c} is null)::int) as {c}" for c in cols)
        rows = con.execute(
            f"select year(snapshot_date) as y, {agg} from {MART} group by y order by y"
        ).fetchall()
        total = con.execute(f"select {agg} from {MART}").fetchone()
    finally:
        con.close()
    assert total is not None
    out = {c: {"all": float(total[i])} for i, c in enumerate(cols)}
    for r in rows:
        for i, c in enumerate(cols):
            out[c][str(r[0])] = float(r[i + 1])
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
