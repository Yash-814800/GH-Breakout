"""Append newly matured live predictions to the training dataset (§9.3 Step 1).

For Monday snapshots whose labels have fully matured
(snapshot_date + 30 days <= latest fully ingested day + 1),
computes realized labels and appends them to:
`training/features_labels/year=YYYY/live-YYYYMMDD.parquet`
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from breakout import paths as P
from breakout.config import Config, get_config
from breakout.duck import connect
from breakout.logging import get_logger

log = get_logger(__name__)

LIVE_FEATURES_DIR = P.DERIVED_DIR / "live" / "features"
TRAINING_DIR = P.DERIVED_DIR / "training"
FEATURES_LABELS_DIR = TRAINING_DIR / "features_labels"


def find_matured_live_mondays(
    cfg: Config,
    latest_ingested: date,
) -> list[tuple[date, Path]]:
    """Find live feature files for Mondays whose 30-day horizon has fully elapsed."""
    if not LIVE_FEATURES_DIR.exists():
        return []

    horizon = cfg.labels.horizon_days
    matured: list[tuple[date, Path]] = []

    for p in sorted(LIVE_FEATURES_DIR.glob("date=*.parquet")):
        try:
            d_str = p.name.replace("date=", "").replace(".parquet", "")
            d = date.fromisoformat(d_str)
        except Exception:
            continue

        # Only weekly Monday snapshots are added to the training set
        if d.weekday() != 0:
            continue

        if d + timedelta(days=horizon) <= latest_ingested + timedelta(days=1):
            matured.append((d, p))

    return matured


def compute_live_labels(
    cfg: Config,
    snapshot_date: date,
    candidates: list[int],
    con: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Compute realized labels for candidate repos on snapshot_date using the warehouse."""
    cand_df = pd.DataFrame({"repo_id": candidates})
    con.register("cand_input", cand_df)

    horizon = cfg.labels.horizon_days
    rel_q = cfg.labels.relative_quantile
    rel_floor = cfg.labels.relative_floor_gain
    abs_gain = cfg.labels.absolute_min_gain

    d_str = snapshot_date.isoformat()

    sql = f"""
    with cands as (
        select repo_id, date '{d_str}' as snapshot_date
        from cand_input
    ),
    daily as (
        select repo_id, day, n_stars from int_repo_star_daily
        where repo_id in (select repo_id from cands)
    ),
    fwd as (
        select c.repo_id, c.snapshot_date, d.day, d.n_stars
        from cands c
        join daily d on d.repo_id = c.repo_id
         and d.day >= c.snapshot_date and d.day < c.snapshot_date + {horizon}
    ),
    gains as (
        select c.repo_id, c.snapshot_date, coalesce(sum(f.n_stars), 0)::integer as gain_30d
        from cands c
        left join fwd f using (repo_id, snapshot_date)
        group by 1, 2
    ),
    thr as (
        select snapshot_date,
               greatest({rel_floor},
                        coalesce(quantile_cont(gain_30d, {rel_q}), {rel_floor})) as threshold_rel,
               count(*) as n_candidates
        from gains
        group by 1
    ),
    hit as (
        select repo_id, snapshot_date, min(day - snapshot_date) as days_to_threshold
        from (
            select f.repo_id, f.snapshot_date, f.day,
                   sum(f.n_stars) over (
                       partition by f.repo_id, f.snapshot_date order by f.day
                   ) as cum
            from fwd f
        ) x
        join thr using (snapshot_date)
        where cum >= threshold_rel
        group by 1, 2
    ),
    trend_days as (
        select s.snapshot_date, count(distinct t.trending_date) as n_days
        from (select distinct snapshot_date from cands) s
        left join (select distinct trending_date from stg_trending where language_filter is null) t
          on t.trending_date >= s.snapshot_date and t.trending_date < s.snapshot_date + 60
        group by 1
    ),
    first_trend as (
        select c.repo_id, c.snapshot_date, min(t.trending_date) as first_trending_date
        from cands c
        join stg_trending t
          on t.repo_id = c.repo_id and t.language_filter is null
         and t.trending_date >= c.snapshot_date and t.trending_date < c.snapshot_date + 60
        group by 1, 2
    )
    select
        g.repo_id,
        g.snapshot_date,
        g.gain_30d,
        t.threshold_rel,
        g.gain_30d >= t.threshold_rel as breakout_rel,
        g.gain_30d >= {abs_gain} as breakout_abs,
        h.days_to_threshold,
        ft.first_trending_date,
        td.n_days >= 54 as trending_covered
    from gains g
    join thr t using (snapshot_date)
    join trend_days td using (snapshot_date)
    left join hit h using (repo_id, snapshot_date)
    left join first_trend ft using (repo_id, snapshot_date)
    order by repo_id
    """
    return con.execute(sql).df()


def append_live_training(
    cfg: Config | None = None,
    warehouse: Path | None = None,
    upload: bool = False,
) -> list[Path]:
    """Find matured Monday snapshots, compute labels, join with features and save."""
    cfg = cfg or get_config(None)
    wh = warehouse or Path(P.WAREHOUSE)

    if not wh.exists():
        log.warning("Warehouse %s does not exist; skipping live training append", wh)
        return []

    con = connect(wh, read_only=True)
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET threads=1")

    appended_files: list[Path] = []
    try:
        # Determine latest ingested day
        res = con.execute("select max(day) from int_repo_star_daily").fetchone()
        latest_day = res[0] if res and res[0] else (datetime.now(UTC).date() - timedelta(days=1))
        if isinstance(latest_day, str):
            latest_day = date.fromisoformat(latest_day)

        matured = find_matured_live_mondays(cfg, latest_day)
        log.info("Found %d matured live Monday snapshots", len(matured))

        for snap_d, feat_file in matured:
            year_dir = FEATURES_LABELS_DIR / f"year={snap_d.year}"
            out_file = year_dir / f"live-{snap_d:%Y%m%d}.parquet"

            if out_file.exists():
                log.info("Live training file %s already exists; skipping", out_file)
                continue

            year_dir.mkdir(parents=True, exist_ok=True)
            feat_df = pd.read_parquet(feat_file)
            cands = [int(r) for r in feat_df["repo_id"].unique()]

            log.info("Computing labels for %d candidates on %s", len(cands), snap_d)
            labels_df = compute_live_labels(cfg, snap_d, cands, con)

            merged = feat_df.merge(labels_df, on=["repo_id", "snapshot_date"], how="inner")
            tmp_file = out_file.with_suffix(".tmp")
            merged.to_parquet(tmp_file, compression="zstd", index=False)
            tmp_file.replace(out_file)

            log.info("Appended %d rows to %s", len(merged), out_file)
            appended_files.append(out_file)

    finally:
        con.close()

    if upload and appended_files:
        from breakout.lake import hf

        api = hf.get_api()
        items = [
            hf.UploadItem(
                f,
                f"training/features_labels/year={f.parent.name.split('=')[-1]}/{f.name}",
            )
            for f in appended_files
        ]
        hf.put_small_files(
            api, cfg, "derived", items, f"Append {len(appended_files)} live training files"
        )

    return appended_files
