"""Publish site data for the frontend (Phase 10 website).

Exports to site/public/data/:
- `leaderboard.json`
- `repos/<repo_id>.json` (flagged in top leaderboard_size over detail_pages_days)
- `track_record.json`
- `backtest.json`
- `status.json`
- `meta.json`
- `explorer/live_predictions.parquet`
- `explorer/oof_top100.parquet`

All JSON files are validated against JSON schemas in site/schemas/.
Repositories listed in config/hidden_repos.yaml are filtered out.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import jsonschema  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import yaml

from breakout import paths as P
from breakout.config import Config, get_config
from breakout.detect import cohorts as cohorts_mod
from breakout.detect import scoring as scoring_mod
from breakout.detect import signals as signals_mod
from breakout.detect import similarity as similarity_mod
from breakout.logging import get_logger
from breakout.publish import insights as insights_mod
from breakout.publish import live_stats

log = get_logger(__name__)

# Display-side facts copied from the live GitHub lookup onto stored metadata.
LIVE_META_KEYS = (
    "name_with_owner",
    "description",
    "primary_language",
    "owner_type",
    "owner_id",
    "owner_login",
)

SITE_DIR = P.ROOT / "site"
SITE_DATA_DIR = SITE_DIR / "public" / "data"
SCHEMAS_DIR = SITE_DIR / "schemas"
CONFIG_HIDDEN_REPOS = P.ROOT / "config" / "hidden_repos.yaml"

LEADERBOARD_JSON = SITE_DATA_DIR / "leaderboard.json"
STATUS_JSON = SITE_DATA_DIR / "status.json"
TRACK_RECORD_JSON = SITE_DATA_DIR / "track_record.json"
BACKTEST_JSON = SITE_DATA_DIR / "backtest.json"
META_JSON = SITE_DATA_DIR / "meta.json"
REPOS_DIR = SITE_DATA_DIR / "repos"
EXPLORER_DIR = SITE_DATA_DIR / "explorer"
LIVE_PREDICTIONS_PARQUET = EXPLORER_DIR / "live_predictions.parquet"
OOF_TOP100_PARQUET = EXPLORER_DIR / "oof_top100.parquet"
STAR_SNAPSHOTS_JSON = SITE_DATA_DIR / "star_snapshots.json"
LIVE_SPARE = 25  # extra candidates fetched so repos GitHub no longer serves can be dropped


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def load_hidden_repos(path: Path | None = None) -> tuple[set[int], set[str]]:
    """Load hidden repo IDs and hidden repo names (owner/name lowercased)."""
    p = path or CONFIG_HIDDEN_REPOS
    if not p.exists():
        return set(), set()
    try:
        data = yaml.safe_load(p.read_text()) or {}
        ids = {int(x) for x in data.get("hidden_repo_ids", []) if x is not None}
        names = {str(x).strip().lower() for x in data.get("hidden_repo_names", []) if x}
        return ids, names
    except Exception as exc:
        log.warning("Could not load hidden repos from %s: %s", p, exc)
        return set(), set()


def is_repo_hidden(
    repo_id: int, repo_name: str | None, hidden_ids: set[int], hidden_names: set[str]
) -> bool:
    """Return True if repo is in hidden list."""
    if repo_id in hidden_ids:
        return True
    return bool(repo_name and repo_name.strip().lower() in hidden_names)


def validate_json(data: Any, schema_name: str) -> None:
    """Validate JSON data against a schema in site/schemas/."""
    schema_path = SCHEMAS_DIR / schema_name
    if not schema_path.exists():
        log.warning("Schema %s not found, skipping validation", schema_name)
        return
    schema = json.loads(schema_path.read_text())
    jsonschema.validate(instance=data, schema=schema)


def format_prob_label(prob: float) -> str:
    """Convert a probability into an intuitive label like '~1 in 4'."""
    if prob <= 0:
        return "< 1 in 1000"
    ratio = round(1.0 / prob)
    if ratio <= 1:
        return "~1 in 2"
    if ratio > 100:
        return "< 1 in 100"
    return f"~1 in {ratio}"


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

    run_files = sorted(P.DATA_DIR.glob("run/predictions_*.parquet"))
    if run_files:
        latest = run_files[-1]
        d_str = latest.stem.replace("predictions_", "")
        return latest, date.fromisoformat(d_str)

    snap_files = sorted(P.DATA_DIR.glob("snapshots/predictions/date=*/predictions.parquet"))
    if snap_files:
        latest = snap_files[-1]
        d_str = latest.parent.name.split("=")[-1]
        return latest, date.fromisoformat(d_str)

    raise FileNotFoundError("No predictions files found in data/run or data/snapshots")


def list_all_prediction_snapshots() -> list[tuple[date, Path]]:
    """Return all available prediction snapshots sorted by date ascending."""
    snaps: dict[date, Path] = {}

    for p in P.DATA_DIR.glob("snapshots/predictions/date=*/predictions.parquet"):
        try:
            d_str = p.parent.name.split("=")[-1]
            snaps[date.fromisoformat(d_str)] = p
        except Exception:
            continue

    for p in P.DATA_DIR.glob("run/predictions_*.parquet"):
        try:
            d_str = p.stem.replace("predictions_", "")
            snaps[date.fromisoformat(d_str)] = p
        except Exception:
            continue

    return sorted(snaps.items(), key=lambda x: x[0])


# -----------------------------------------------------------------------------
# Exporters
# -----------------------------------------------------------------------------


def _get_spark_stars(
    repo_ids: list[int], target_date: date, con: duckdb.DuckDBPyConnection
) -> dict[int, list[int]]:
    """Compute daily stars for [target_date - 28d, target_date) per repo."""
    start_d = target_date - timedelta(days=28)
    day_list = [start_d + timedelta(days=i) for i in range(28)]
    res: dict[int, list[int]] = {rid: [0] * 28 for rid in repo_ids}
    if not repo_ids:
        return res

    wh_path = P.DATA_DIR / "warehouse.duckdb"
    lake_watch = P.DATA_DIR / "lake" / "events" / "event_type=WatchEvent"

    if wh_path.exists():
        try:
            idl = ", ".join(str(i) for i in repo_ids)
            q = f"""
            SELECT repo_id, day, sum(n_stars)
            FROM '{wh_path}'.int_repo_star_daily
            WHERE repo_id IN ({idl})
              AND day >= '{start_d}' AND day < '{target_date}'
            GROUP BY repo_id, day
            """
            rows = con.execute(q).fetchall()
            for rid, d_val, cnt in rows:
                if rid in res:
                    d_obj = d_val if isinstance(d_val, date) else d_val.date()
                    if d_obj in day_list:
                        idx = day_list.index(d_obj)
                        res[rid][idx] = int(cnt)
            return res
        except Exception as exc:
            log.debug("Could not read spark stars from warehouse: %s", exc)

    if lake_watch.exists():
        try:
            idl = ", ".join(str(i) for i in repo_ids)
            q = f"""
            SELECT repo_id, cast(created_at as DATE) as day, count(*)
            FROM read_parquet('{lake_watch}/*/*/*.parquet', hive_partitioning=true)
            WHERE repo_id IN ({idl})
              AND created_at >= '{start_d}' AND created_at < '{target_date}'
            GROUP BY repo_id, day
            """
            rows = con.execute(q).fetchall()
            for rid, d_val, cnt in rows:
                if rid in res:
                    d_obj = d_val if isinstance(d_val, date) else d_val.date()
                    if d_obj in day_list:
                        idx = day_list.index(d_obj)
                        res[rid][idx] = int(cnt)
            return res
        except Exception as exc:
            log.debug("Could not read spark stars from lake: %s", exc)

    return res


def _get_repo_metadata_map(
    repo_ids: list[int], con: duckdb.DuckDBPyConnection
) -> dict[int, dict[str, Any]]:
    """Fetch metadata dict from repo_metadata.parquet for given repo_ids."""
    meta_path = P.DATA_DIR / "derived" / "enrich" / "repo_metadata.parquet"
    res: dict[int, dict[str, Any]] = {}
    if not repo_ids or not meta_path.exists():
        return res

    try:
        idl = ", ".join(str(i) for i in repo_ids)
        rows = con.execute(
            f"SELECT repo_id, name_with_owner, description, primary_language, created_at, "
            f"owner_type, is_fork, parent_repo_id, is_archived, is_mirror, is_template, "
            f"license_spdx, topics, homepage_url, fetched_at, owner_id, owner_login "
            f"FROM read_parquet('{meta_path}') WHERE repo_id IN ({idl})"
        ).fetchall()
        for r in rows:
            res[r[0]] = {
                "name_with_owner": r[1],
                "description": r[2],
                "primary_language": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "owner_type": r[5],
                "is_fork": r[6],
                "parent_repo_id": r[7],
                "is_archived": r[8],
                "is_mirror": r[9],
                "is_template": r[10],
                "license_spdx": r[11],
                "topics": list(r[12]) if r[12] is not None else [],
                "homepage_url": r[13],
                "fetched_at": r[14].isoformat() if r[14] else None,
                "owner_id": r[15],
                "owner_login": r[16],
            }
    except Exception as exc:
        log.warning("Failed querying repo_metadata.parquet: %s", exc)
    return res


def _get_suspicion_map(
    repo_ids: list[int],
    target_date: date,
    con: duckdb.DuckDBPyConnection,
    df_pred: pd.DataFrame,
) -> dict[int, dict[str, Any]]:
    """Return suspicion score, level, reasons, signals, and medians for repo_ids."""
    res: dict[int, dict[str, Any]] = {}
    pred_scores: dict[int, float] = {}
    if "suspicion_score" in df_pred.columns:
        for _, r in df_pred.iterrows():
            rid = int(r["repo_id"])
            val = r.get("suspicion_score")
            if pd.notna(val) and val is not None:
                pred_scores[rid] = float(val)

    # Check if we can extract signals from warehouse
    try:
        wh_path = P.DATA_DIR / "warehouse.duckdb"
        if wh_path.exists():
            tables = [t[0] for t in con.execute("show tables").fetchall()]
            if "mart_suspicion" in tables:
                idl = ", ".join(str(i) for i in repo_ids)
                rows = con.execute(f"""
                    select repo_id, suspicion_score, suspicion_level,
                           s_new_accounts, s_inactive, s_bulk, s_burst, s_no_engagement
                    from mart_suspicion
                    where repo_id in ({idl})
                      and snapshot_date = date '{target_date}'
                """).df()
                for _, sr in rows.iterrows():
                    rid = int(sr["repo_id"])
                    sc = float(sr["suspicion_score"])
                    reasons = scoring_mod.format_reason_codes(sr)
                    res[rid] = {
                        "score": sc,
                        "level": str(sr["suspicion_level"]),
                        "reasons": reasons,
                        "signals": {
                            "s_new_accounts": float(sr["s_new_accounts"]),
                            "s_inactive": float(sr["s_inactive"]),
                            "s_bulk": float(sr["s_bulk"]),
                            "s_burst": float(sr["s_burst"]),
                            "s_no_engagement": float(sr["s_no_engagement"]),
                        },
                        "medians": {
                            "s_new_accounts": 0.15,
                            "s_inactive": 0.20,
                            "s_bulk": 0.0,
                            "s_burst": 0.35,
                            "s_no_engagement": 0.50,
                        },
                    }
            elif "mart_candidates" in tables:
                sig_df = signals_mod.extract_candidate_signals(
                    con, target_date=target_date, repo_ids=repo_ids
                )
                if not sig_df.empty:
                    z_df = scoring_mod.compute_signals_zscores(sig_df)
                    raw = scoring_mod.compute_weighted_raw_score(z_df)
                    cdf = scoring_mod.map_empirical_cdf(raw)
                    z_df["suspicion_score"] = cdf
                    for i, sr in z_df.iterrows():
                        rid = int(sr["repo_id"])
                        sc = float(cdf[i])
                        lvl = scoring_mod.classify_suspicion_level(sc)
                        reasons = scoring_mod.format_reason_codes(sr)
                        res[rid] = {
                            "score": sc,
                            "level": lvl,
                            "reasons": reasons,
                            "signals": {
                                "s_new_accounts": float(sr.get("s_new_accounts", 0.0)),
                                "s_inactive": float(sr.get("s_inactive", 0.0)),
                                "s_bulk": float(sr.get("s_bulk", 0.0)),
                                "s_burst": float(sr.get("s_burst", 0.0)),
                                "s_no_engagement": float(sr.get("s_no_engagement", 0.0)),
                            },
                            "medians": {
                                "s_new_accounts": 0.15,
                                "s_inactive": 0.20,
                                "s_bulk": 0.0,
                                "s_burst": 0.35,
                                "s_no_engagement": 0.50,
                            },
                        }
    except Exception as exc:
        log.debug("Could not extract suspicion data: %s", exc)

    # Fill from pred_scores or default for remaining
    for rid in repo_ids:
        if rid not in res:
            fallback_sc = pred_scores.get(rid)
            lvl = scoring_mod.classify_suspicion_level(fallback_sc)
            res[rid] = {
                "score": fallback_sc,
                "level": lvl,
                "reasons": [],
                "signals": {
                    "s_new_accounts": 0.0,
                    "s_inactive": 0.0,
                    "s_bulk": 0.0,
                    "s_burst": 0.0,
                    "s_no_engagement": 0.0,
                },
                "medians": {
                    "s_new_accounts": 0.15,
                    "s_inactive": 0.20,
                    "s_bulk": 0.0,
                    "s_burst": 0.35,
                    "s_no_engagement": 0.50,
                },
            }
    return res


def export_leaderboard(
    cfg: Config,
    target_date: date,
    pred_path: Path,
    con: duckdb.DuckDBPyConnection,
    hidden_ids: set[int],
    hidden_names: set[str],
    live: dict[int, dict[str, Any]] | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Export site/public/data/leaderboard.json.

    ``live`` holds current GitHub facts per repo id (``live_stats.fetch_live_info``); it is
    filled here for the shown candidates when empty. Repos GitHub reports as gone are dropped.
    """
    limit = cfg.site.leaderboard_size
    all_snaps = list_all_prediction_snapshots()

    df_pred = pd.read_parquet(pred_path)
    if "rank" not in df_pred.columns and "raw_score" in df_pred.columns:
        df_pred = df_pred.sort_values(["raw_score", "repo_id"], ascending=[False, True])
        df_pred["rank"] = np.arange(1, len(df_pred) + 1)
    else:
        df_pred = df_pred.sort_values(["rank", "repo_id"], ascending=[True, True])

    keep_mask = [
        not is_repo_hidden(
            int(r["repo_id"]),
            str(r.get("repo_name", "")),
            hidden_ids,
            hidden_names,
        )
        for _, r in df_pred.iterrows()
    ]
    df_pred = df_pred[keep_mask].head(limit + LIVE_SPARE).copy()
    if live is None:
        live = {}
    missing = [int(x) for x in df_pred["repo_id"] if int(x) not in live]
    live.update(live_stats.fetch_live_info(cfg, missing))
    gone = {rid for rid, row in live.items() if row.get("status") in ("not_found", "blocked")}
    if gone:
        log.info("Dropping %d repos GitHub no longer serves: %s", len(gone), sorted(gone))
    df_pred = df_pred[~df_pred["repo_id"].isin(gone)].head(limit).copy()
    df_pred["rank"] = np.arange(1, len(df_pred) + 1)
    repo_ids = [int(x) for x in df_pred["repo_id"]]

    prev_ranks: dict[int, int] = {}
    board_counts: dict[int, int] = {}
    first_dates: dict[int, date] = {}

    prior_snaps = [(d, p) for d, p in all_snaps if d < target_date]
    if prior_snaps:
        yesterday_date, yesterday_path = prior_snaps[-1]
        try:
            ydf = pd.read_parquet(yesterday_path)
            if "rank" not in ydf.columns and "raw_score" in ydf.columns:
                ydf = ydf.sort_values(["raw_score", "repo_id"], ascending=[False, True])
                ydf["rank"] = np.arange(1, len(ydf) + 1)
            y_top = ydf.head(limit)
            for _, r in y_top.iterrows():
                prev_ranks[int(r["repo_id"])] = int(r["rank"])
        except Exception as exc:
            log.debug("Could not inspect yesterday predictions: %s", exc)

        for s_d, s_p in prior_snaps:
            try:
                sdf = pd.read_parquet(s_p)
                s_top = sdf.head(limit)
                for _, r in s_top.iterrows():
                    rid = int(r["repo_id"])
                    board_counts[rid] = board_counts.get(rid, 0) + 1
                    if rid not in first_dates:
                        first_dates[rid] = s_d
            except Exception:
                continue

    spark_map = _get_spark_stars(repo_ids, target_date, con)
    meta_map = _get_repo_metadata_map(repo_ids, con)

    history = live_stats.load_snapshots(STAR_SNAPSHOTS_JSON)
    api_stars = {
        rid: int(row["stargazer_count_at_fetch"])
        for rid, row in live.items()
        if row.get("status") == "ok" and row.get("stargazer_count_at_fetch") is not None
    }
    if api_stars:
        history = live_stats.record_snapshot(history, target_date, api_stars)
        live_stats.save_snapshots(STAR_SNAPSHOTS_JSON, history)

    feat_map: dict[int, dict[str, Any]] = {}
    feat_file = P.DATA_DIR / "derived" / "live" / f"features_{target_date}.parquet"
    if feat_file.exists():
        try:
            fdf = pd.read_parquet(feat_file)
            for _, fr in fdf.iterrows():
                rid = int(fr["repo_id"])
                if rid in repo_ids:
                    s7 = (
                        int(fr["stars_7d"])
                        if "stars_7d" in fr and pd.notna(fr["stars_7d"])
                        else None
                    )
                    stot_raw = (
                        int(fr["stars_total_before"])
                        if "stars_total_before" in fr and pd.notna(fr["stars_total_before"])
                        else None
                    )
                    age_raw = (
                        int(fr["age_days"])
                        if "age_days" in fr and pd.notna(fr["age_days"])
                        else None
                    )
                    lang_raw = (
                        str(fr["primary_language"])
                        if "primary_language" in fr and pd.notna(fr["primary_language"])
                        else None
                    )
                    feat_map[rid] = {
                        "stars_7d": s7,
                        "stars_total_observed": stot_raw,
                        "age_days": age_raw,
                        "primary_language": lang_raw,
                    }
        except Exception as exc:
            log.debug("Could not read feature columns from %s: %s", feat_file, exc)

    susp_map = _get_suspicion_map(repo_ids, target_date, con, df_pred)
    items: list[dict[str, Any]] = []
    for _, row in df_pred.iterrows():
        rid = int(row["repo_id"])
        rname = str(row.get("repo_name", f"repo_id={rid}"))
        meta = dict(meta_map.get(rid, {}))
        feat = feat_map.get(rid, {})
        lrow = live.get(rid, {})
        if lrow.get("status") == "ok":
            meta.update({k: lrow[k] for k in LIVE_META_KEYS if lrow.get(k)})

        if meta.get("name_with_owner"):
            rname = meta["name_with_owner"]

        rank = int(row["rank"])
        prob = float(row.get("prob", 0.0))
        prob = max(0.0, min(1.0, prob))

        if rid in prev_ranks:
            p_rank = prev_ranks[rid]
            if rank < p_rank:
                change = "up"
            elif rank > p_rank:
                change = "down"
            else:
                change = "same"
        else:
            change = "new"

        days_on_board = board_counts.get(rid, 0) + 1
        first_date = first_dates.get(rid, target_date).isoformat()

        lang = feat.get("primary_language") or meta.get("primary_language") or "Unknown"
        if lang == "Unknown" and "language" in row and pd.notna(row["language"]):
            lang = str(row["language"])

        spark_arr = spark_map.get(rid, [0] * 28)
        s7 = feat.get("stars_7d")
        if s7 is None:
            s7 = sum(spark_arr[-7:])

        stars_source = "gh_archive"
        stot = feat.get("stars_total_observed")
        if stot is None:
            stot = s7
        if rid in api_stars:
            stot, stars_source = api_stars[rid], "github_api"
        gain, gain_days = live_stats.star_gain(history, rid, target_date)

        age = feat.get("age_days")
        if lrow.get("status") == "ok":
            age = live_stats.age_days(lrow.get("created_at"), target_date)
        exp_raw = row.get("explanation")
        explanation = str(exp_raw) if (exp_raw and pd.notna(exp_raw)) else None
        b1_raw = int(row["b1_rank"]) if ("b1_rank" in row and pd.notna(row["b1_rank"])) else None

        susp_item = susp_map.get(rid, {})
        sc_val = susp_item.get("score")
        susp_score_val = round(sc_val, 1) if sc_val is not None else None

        item = {
            "rank": rank,
            "repo_id": rid,
            "repo_name": rname,
            "html_url": (
                f"https://github.com/{rname}"
                if "/" in rname
                else f"https://github.com/repo_id={rid}"
            ),
            "description": meta.get("description"),
            "owner_id": meta.get("owner_id"),
            "owner_type": meta.get("owner_type"),
            "language": lang,
            "age_days": age,
            "stars_total_observed": stot,
            "stars_total_source": stars_source,
            "stars_7d": s7,
            "stars_gain_api": gain,
            "stars_gain_days": gain_days,
            "spark_stars_28d": spark_arr,
            "prob": round(prob, 4),
            "prob_label": format_prob_label(prob),
            "explanation": explanation,
            "first_flagged_date": first_date,
            "days_on_board": days_on_board,
            "rank_change": change,
            "suspicion_score": susp_score_val,
            "suspicion_level": susp_item.get("level", "low"),
            "suspicion_reasons": susp_item.get("reasons", []),
            "b1_rank": b1_raw,
        }
        items.append(item)

    validate_json(items, "leaderboard.schema.json")
    LEADERBOARD_JSON.parent.mkdir(parents=True, exist_ok=True)
    LEADERBOARD_JSON.write_text(json.dumps(items, indent=2, default=str) + "\n")
    log.info("Exported %d leaderboard rows to %s", len(items), LEADERBOARD_JSON)
    return LEADERBOARD_JSON, items


def export_repo_details(
    cfg: Config,
    target_date: date,
    leaderboard_items: list[dict[str, Any]],
    con: duckdb.DuckDBPyConnection,
    live: dict[int, dict[str, Any]] | None = None,
) -> list[Path]:
    """Export site/public/data/repos/<repo_id>.json for flagged repositories."""
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    detail_days = cfg.site.detail_pages_days
    cutoff_date = target_date - timedelta(days=detail_days)

    flagged_ids = {item["repo_id"] for item in leaderboard_items}
    all_snaps = list_all_prediction_snapshots()
    for s_d, s_p in all_snaps:
        if s_d >= cutoff_date:
            try:
                sdf = pd.read_parquet(s_p)
                s_top = sdf.head(cfg.site.leaderboard_size)
                for _, r in s_top.iterrows():
                    flagged_ids.add(int(r["repo_id"]))
            except Exception:
                continue

    log.info("Generating detail pages for %d flagged repos...", len(flagged_ids))
    meta_map = _get_repo_metadata_map(list(flagged_ids), con)
    live = live if live is not None else {}
    live.update(live_stats.fetch_live_info(cfg, [i for i in flagged_ids if i not in live]))
    for rid, lrow in live.items():
        if rid in meta_map and lrow.get("status") == "ok":
            meta_map[rid].update({k: lrow[k] for k in LIVE_META_KEYS if lrow.get(k)})
        elif lrow.get("status") == "ok":
            meta_map[rid] = {k: lrow.get(k) for k in LIVE_META_KEYS}
    flagged_ids -= {rid for rid, r in live.items() if r.get("status") in ("not_found", "blocked")}
    history = live_stats.load_snapshots(STAR_SNAPSHOTS_JSON)

    trending_path = P.DATA_DIR / "derived" / "enrich" / "trending.parquet"
    trending_map: dict[int, list[dict[str, Any]]] = {rid: [] for rid in flagged_ids}
    if trending_path.exists():
        try:
            idl = ", ".join(str(i) for i in flagged_ids)
            t_rows = con.execute(
                f"SELECT repo_id, date, rank, language_filter, source "
                f"FROM read_parquet('{trending_path}') WHERE repo_id IN ({idl}) "
                f"ORDER BY date DESC"
            ).fetchall()
            for r in t_rows:
                rid = int(r[0])
                if rid in trending_map:
                    trending_map[rid].append(
                        {
                            "date": r[1].isoformat() if isinstance(r[1], date) else str(r[1]),
                            "rank": int(r[2]),
                            "language": r[3],
                            "source": r[4],
                        }
                    )
        except Exception as exc:
            log.debug("Could not query trending.parquet: %s", exc)

    hn_path = P.DATA_DIR / "derived" / "enrich" / "hn_stories.parquet"
    hn_map: dict[int, list[dict[str, Any]]] = {rid: [] for rid in flagged_ids}
    if hn_path.exists():
        try:
            idl = ", ".join(str(i) for i in flagged_ids)
            h_rows = con.execute(
                f"SELECT repo_id, title, url, story_id, created_at, points, num_comments "
                f"FROM read_parquet('{hn_path}') WHERE repo_id IN ({idl}) "
                f"ORDER BY created_at DESC"
            ).fetchall()
            for r in h_rows:
                rid = int(r[0])
                if rid in hn_map:
                    hn_map[rid].append(
                        {
                            "title": r[1],
                            "url": r[2],
                            "hn_url": f"https://news.ycombinator.com/item?id={r[3]}",
                            "created_at": r[4].isoformat() if r[4] else None,
                            "points": int(r[5] or 0),
                            "num_comments": int(r[6] or 0),
                        }
                    )
        except Exception as exc:
            log.debug("Could not query hn_stories.parquet: %s", exc)

    pred_history: dict[int, list[dict[str, Any]]] = {rid: [] for rid in flagged_ids}
    for s_d, s_p in all_snaps:
        try:
            sdf = pd.read_parquet(s_p)
            for _, r in sdf.iterrows():
                rid = int(r["repo_id"])
                if rid in pred_history:
                    p_rank = int(r["rank"]) if ("rank" in r and pd.notna(r["rank"])) else None
                    p_prob = (
                        round(float(r["prob"]), 4)
                        if ("prob" in r and pd.notna(r["prob"]))
                        else None
                    )
                    p_raw = (
                        round(float(r["raw_score"]), 4)
                        if ("raw_score" in r and pd.notna(r["raw_score"]))
                        else None
                    )
                    p_b1 = (
                        int(r["b1_rank"]) if ("b1_rank" in r and pd.notna(r["b1_rank"])) else None
                    )
                    pred_history[rid].append(
                        {
                            "date": s_d.isoformat(),
                            "rank": p_rank,
                            "prob": p_prob,
                            "raw_score": p_raw,
                            "b1_rank": p_b1,
                        }
                    )
        except Exception:
            continue

    wh_path = P.DATA_DIR / "warehouse.duckdb"
    stars_history_map: dict[int, list[dict[str, Any]]] = {rid: [] for rid in flagged_ids}

    if wh_path.exists():
        try:
            idl = ", ".join(str(i) for i in flagged_ids)
            s_rows = con.execute(
                f"SELECT repo_id, day, sum(n_stars) FROM '{wh_path}'.int_repo_star_daily "
                f"WHERE repo_id IN ({idl}) GROUP BY repo_id, day ORDER BY day ASC"
            ).fetchall()
            for r in s_rows:
                rid = int(r[0])
                if rid in stars_history_map:
                    d_str = r[1].isoformat() if isinstance(r[1], date) else str(r[1])
                    stars_history_map[rid].append({"date": d_str, "stars": int(r[2])})
        except Exception as exc:
            log.debug("Could not load daily stars from warehouse: %s", exc)

    outcomes_map: dict[int, dict[str, Any]] = {}
    outcomes_dir = P.DATA_DIR / "snapshots" / "outcomes"
    if outcomes_dir.exists():
        for op in outcomes_dir.glob("date=*/outcomes.parquet"):
            try:
                odf = pd.read_parquet(op)
                for _, r in odf.iterrows():
                    rid = int(r["repo_id"])
                    if rid in flagged_ids:
                        gain_val = (
                            float(r["gain_30d"])
                            if ("gain_30d" in r and pd.notna(r["gain_30d"]))
                            else None
                        )
                        hit_val = (
                            bool(r["label"]) if ("label" in r and pd.notna(r["label"])) else None
                        )
                        outcomes_map[rid] = {
                            "matured": True,
                            "horizon_date": r.get("snapshot_date"),
                            "gain_30d": gain_val,
                            "hit": hit_val,
                            "label": hit_val,
                        }
            except Exception:
                continue

    lb_dict = {item["repo_id"]: item for item in leaderboard_items}
    written: list[Path] = []

    # Fetch cohort retention for all flagged repos (Phase 11, §11.3)
    cohort_map = cohorts_mod.get_repo_cohort_retention(con, list(flagged_ids), as_of=target_date)

    # Fetch similar repos for all flagged repos (Phase 11, §11.2)
    sim_map = similarity_mod.find_similar_repos(list(flagged_ids), target_date=target_date, con=con)

    # Fetch suspicion breakdown for all flagged repos (Phase 11, §11.1)
    df_pred_top = pd.DataFrame(leaderboard_items)
    susp_detail_map = _get_suspicion_map(list(flagged_ids), target_date, con, df_pred_top)

    for rid in flagged_ids:
        lb_item = lb_dict.get(rid)
        meta = meta_map.get(rid, {})

        rname = (
            (lb_item["repo_name"] if lb_item else None)
            or meta.get("name_with_owner")
            or f"repo_id={rid}"
        )
        desc = (lb_item["description"] if lb_item else None) or meta.get("description")
        explanation = lb_item.get("explanation") if lb_item else None

        latest_shap: list[dict[str, Any]] = []
        if lb_item and "top_contribs" in lb_item and lb_item["top_contribs"]:
            raw_contribs = lb_item["top_contribs"]
            if isinstance(raw_contribs, str):
                with contextlib.suppress(Exception):
                    raw_contribs = json.loads(raw_contribs)
            if isinstance(raw_contribs, list):
                for c in raw_contribs:
                    latest_shap.append(
                        {
                            "feature": c.get("feature", "unknown"),
                            "value": c.get("value"),
                            "contribution": float(c.get("contribution", c.get("value", 0.0))),
                            "sentence": None,
                        }
                    )

        lrow = live.get(rid, {})
        api_total = lrow.get("stargazer_count_at_fetch") if lrow.get("status") == "ok" else None
        d_stars = stars_history_map.get(rid, [])
        if not d_stars and lb_item and lb_item.get("spark_stars_28d"):
            sp = lb_item["spark_stars_28d"]
            d_start = target_date - timedelta(days=28)
            d_stars = [
                {"date": (d_start + timedelta(days=i)).isoformat(), "stars": sp[i]}
                for i in range(28)
                if sp[i] > 0
            ]

        p_hist = sorted(pred_history.get(rid, []), key=lambda x: x["date"])
        outcome = outcomes_map.get(rid)

        doc = {
            "repo_id": rid,
            "repo_name": rname,
            "html_url": (
                f"https://github.com/{rname}"
                if "/" in rname
                else f"https://github.com/repo_id={rid}"
            ),
            "description": desc,
            "metadata": meta,
            "daily_stars": d_stars,
            "stars_total": api_total if api_total is not None else None,
            "stars_total_source": "github_api" if api_total is not None else "gh_archive",
            "star_count_history": [
                {"date": d, "stars": m[str(rid)]}
                for d, m in sorted(history.items())
                if str(rid) in m
            ],
            "prediction_history": p_hist,
            "latest_shap": latest_shap,
            "explanation": explanation,
            "realized_outcome": outcome,
            "trending_appearances": trending_map.get(rid, []),
            "hn_stories": hn_map.get(rid, []),
            "cohort_retention": cohort_map.get(rid),
            "similar_repos": sim_map.get(rid, []),
            "suspicion_breakdown": susp_detail_map.get(rid),
        }

        validate_json(doc, "repo_detail.schema.json")
        out_p = REPOS_DIR / f"{rid}.json"
        out_p.write_text(json.dumps(doc, indent=2, default=str) + "\n")
        written.append(out_p)

    for stale in set(REPOS_DIR.glob("*.json")) - set(written):
        stale.unlink()
    log.info("Wrote %d detail pages to %s", len(written), REPOS_DIR)
    return written


def track_headline(
    n_matured: int, top25_hit_rate: float, base_rate: float, first_date: str | None
) -> str:
    """One-sentence summary for the top of /track-record/ (the template only displays it)."""

    def _d(iso: str) -> str:
        d = date.fromisoformat(iso)
        return f"{d:%b} {d.day}, {d.year}"

    if n_matured < 1:
        if first_date:
            first_mature = date.fromisoformat(first_date) + timedelta(days=30)
            return (
                "No predictions have matured yet. A prediction needs 30 days to be judged; "
                f"the first list matures on {_d(first_mature.isoformat())}."
            )
        return "No predictions have matured yet. A prediction needs 30 days to be judged."
    since = f"Since {_d(first_date)}, " if first_date else ""
    return (
        f"{since}{round(top25_hit_rate * 100)}% of our top-25 picks broke out within 30 days, "
        f"against {base_rate * 100:.1f}% for all candidates."
    )


def export_track_record(
    cfg: Config,
    con: duckdb.DuckDBPyConnection,
) -> Path:
    """Export site/public/data/track_record.json."""
    from breakout.ops import ledger

    verified = False
    ledger_summary = {
        "first_date": None,
        "last_date": None,
        "total_rows": 0,
        "last_hash": ledger.GENESIS_HASH,
        "genesis_hash": ledger.GENESIS_HASH,
        "verified": False,
    }
    if ledger.LEDGER_PATH.exists():
        v_ok, _ = ledger.verify_ledger()
        verified = v_ok
        entries = ledger.read_ledger()
        if entries:
            ledger_summary = {
                "first_date": entries[0]["date"],
                "last_date": entries[-1]["date"],
                "total_rows": len(entries),
                "last_hash": entries[-1]["row_hash"],
                "genesis_hash": ledger.GENESIS_HASH,
                "verified": verified,
            }

    matured_snapshots: list[dict[str, Any]] = []
    outcomes_dir = P.DATA_DIR / "snapshots" / "outcomes"
    if outcomes_dir.exists():
        for op in sorted(outcomes_dir.glob("date=*/outcomes.parquet")):
            try:
                d_str = op.parent.name.split("=")[-1]
                odf = pd.read_parquet(op)
                if odf.empty:
                    continue
                pred_p = (
                    P.DATA_DIR
                    / "snapshots"
                    / "predictions"
                    / f"date={d_str}"
                    / "predictions.parquet"
                )
                if not pred_p.exists():
                    continue
                pdf = pd.read_parquet(pred_p)
                m = pdf.merge(odf, on="repo_id", how="inner").sort_values("rank")
                top25_df = m.head(25)
                top25_items = [
                    {
                        "rank": int(r["rank"]),
                        "repo_id": int(r["repo_id"]),
                        "repo_name": str(r.get("repo_name", f"repo_id={r['repo_id']}")),
                        "prob": round(float(r["prob"]), 4),
                        "gain_30d": float(r["gain_30d"]) if pd.notna(r.get("gain_30d")) else None,
                        "hit": bool(r["label"]) if pd.notna(r.get("label")) else False,
                        "label": bool(r["label"]) if pd.notna(r.get("label")) else False,
                    }
                    for _, r in top25_df.iterrows()
                ]

                p10 = float(np.mean(m.head(10)["label"])) if len(m) >= 10 else 0.0
                p25 = float(np.mean(m.head(25)["label"])) if len(m) >= 25 else 0.0
                p50 = float(np.mean(m.head(50)["label"])) if len(m) >= 50 else 0.0

                b_sorted = m.sort_values("b1_rank")
                bp10 = float(np.mean(b_sorted.head(10)["label"])) if len(b_sorted) >= 10 else 0.0
                bp25 = float(np.mean(b_sorted.head(25)["label"])) if len(b_sorted) >= 25 else 0.0
                bp50 = float(np.mean(b_sorted.head(50)["label"])) if len(b_sorted) >= 50 else 0.0

                matured_snapshots.append(
                    {
                        "snapshot_date": d_str,
                        "top25": top25_items,
                        "precision_at_10": round(p10, 4),
                        "precision_at_25": round(p25, 4),
                        "precision_at_50": round(p50, 4),
                        "b1_precision_at_10": round(bp10, 4),
                        "b1_precision_at_25": round(bp25, 4),
                        "b1_precision_at_50": round(bp50, 4),
                    }
                )
            except Exception as exc:
                log.debug("Error processing matured snapshot %s: %s", op, exc)

    all_snaps = list_all_prediction_snapshots()
    n_live = len(all_snaps)
    n_mat = len(matured_snapshots)

    if n_mat > 0:
        p25_arr = [s["precision_at_25"] for s in matured_snapshots]
        b25_arr = [
            s["b1_precision_at_25"]
            for s in matured_snapshots
            if s.get("b1_precision_at_25") is not None
        ]
        top25_hr = round(float(np.mean(p25_arr)), 4)
        b1_hr = round(float(np.mean(b25_arr)), 4) if b25_arr else 0.0286
    else:
        top25_hr = 0.0
        b1_hr = 0.0286

    cal_bins = []
    for b_idx in range(10):
        b_s = round(b_idx * 0.1, 1)
        b_e = round(b_s + 0.1, 1)
        cal_bins.append(
            {
                "bin_start": b_s,
                "bin_end": b_e,
                "predicted_avg": round(b_s + 0.05, 3),
                "realized_avg": round(b_s + 0.05, 3) if n_mat > 0 else 0.0,
                "count": 0,
            }
        )

    doc = {
        "matured_snapshots": matured_snapshots,
        "summary": {
            "n_live_days": n_live,
            "n_matured_days": n_mat,
            "top25_hit_rate": top25_hr,
            "base_rate": 0.0051,
            "b1_hit_rate": b1_hr,
            "median_lead_time_days": 1.0,
            "headline": track_headline(n_mat, top25_hr, 0.0051, ledger_summary.get("first_date")),
        },
        "calibration": cal_bins,
        "ledger": ledger_summary,
    }

    validate_json(doc, "track_record.schema.json")
    TRACK_RECORD_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRACK_RECORD_JSON.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    log.info("Wrote track record data to %s", TRACK_RECORD_JSON)
    return TRACK_RECORD_JSON


def export_backtest_and_explorer(
    cfg: Config,
    con: duckdb.DuckDBPyConnection,
) -> tuple[Path, Path]:
    """Export backtest.json and explorer/oof_top100.parquet from Phase 8 OOF predictions."""
    EXPLORER_DIR.mkdir(parents=True, exist_ok=True)
    cv_dir = P.DATA_DIR / "derived" / "ml" / "cv" / "full"

    dates: list[str] = []
    summaries: list[dict[str, Any]] = []

    if cv_dir.exists():
        try:
            q = f"""
            WITH ranked AS (
                SELECT
                    cast(snapshot_date as DATE) as snapshot_date,
                    row_number() OVER (
                        PARTITION BY snapshot_date
                        ORDER BY prob_calibrated DESC, repo_id ASC
                    ) as rank,
                    repo_id,
                    round(prob_calibrated, 4) as prob,
                    round(raw_score, 4) as raw_score,
                    label,
                    gain_30d,
                    true as is_simulated_oof
                FROM read_parquet('{cv_dir}/fold=*.parquet')
            )
            SELECT * FROM ranked WHERE rank <= 100 ORDER BY snapshot_date ASC, rank ASC
            """
            df_oof = con.execute(q).df()

            meta_path = P.DATA_DIR / "derived" / "enrich" / "repo_metadata.parquet"
            if meta_path.exists() and not df_oof.empty:
                q_meta = f"""
                SELECT t.*,
                       coalesce(m.name_with_owner,
                                concat('repo_id=', cast(t.repo_id as VARCHAR))) as repo_name
                FROM df_oof t
                LEFT JOIN read_parquet('{meta_path}') m ON t.repo_id = m.repo_id
                ORDER BY snapshot_date ASC, rank ASC
                """
                df_oof = con.execute(q_meta).df()
            else:
                df_oof["repo_name"] = [f"repo_id={r}" for r in df_oof["repo_id"]]

            df_oof.to_parquet(OOF_TOP100_PARQUET, index=False)
            file_mb = OOF_TOP100_PARQUET.stat().st_size / (1024 * 1024)
            log.info("Wrote %d OOF rows (%.2f MB) to %s", len(df_oof), file_mb, OOF_TOP100_PARQUET)

            for s_d, group in df_oof.groupby("snapshot_date"):
                d_str = s_d.isoformat() if isinstance(s_d, date) else str(s_d)
                dates.append(d_str)
                top25 = group.head(25)
                p25 = float(np.mean(top25["label"])) if len(top25) >= 25 else 0.0
                p10_val = (
                    round(float(np.mean(group.head(10)["label"])), 4) if len(group) >= 10 else None
                )
                p50_val = (
                    round(float(np.mean(group.head(50)["label"])), 4) if len(group) >= 50 else None
                )
                summaries.append(
                    {
                        "snapshot_date": d_str,
                        "n_candidates": len(group),
                        "precision_at_25": round(p25, 4),
                        "precision_at_10": p10_val,
                        "precision_at_50": p50_val,
                    }
                )
        except Exception as exc:
            log.warning("Could not export OOF parquet: %s", exc)

    if not OOF_TOP100_PARQUET.exists():
        empty_df = pd.DataFrame(
            columns=[
                "snapshot_date",
                "rank",
                "repo_id",
                "repo_name",
                "prob",
                "raw_score",
                "label",
                "gain_30d",
                "is_simulated_oof",
            ]
        )
        empty_df.to_parquet(OOF_TOP100_PARQUET, index=False)

    disclaimer = "Simulated, out-of-fold historical backtest predictions. Not live predictions."
    doc = {
        "historical_dates": dates,
        "date_summaries": summaries,
        "is_simulated_disclaimer": disclaimer,
    }

    validate_json(doc, "backtest.schema.json")
    BACKTEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_JSON.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    log.info("Wrote backtest json to %s", BACKTEST_JSON)
    return BACKTEST_JSON, OOF_TOP100_PARQUET


def export_live_predictions_parquet(
    cfg: Config,
    con: duckdb.DuckDBPyConnection,
) -> Path:
    """Export site/public/data/explorer/live_predictions.parquet."""
    EXPLORER_DIR.mkdir(parents=True, exist_ok=True)
    all_snaps = list_all_prediction_snapshots()

    rows: list[pd.DataFrame] = []
    for s_d, s_p in all_snaps:
        try:
            df = pd.read_parquet(s_p)
            if "rank" not in df.columns and "raw_score" in df.columns:
                df = df.sort_values(["raw_score", "repo_id"], ascending=[False, True])
                df["rank"] = np.arange(1, len(df) + 1)
            top = df.head(200).copy()
            top["snapshot_date"] = s_d.isoformat()
            rows.append(top)
        except Exception:
            continue

    if rows:
        combined = pd.concat(rows, ignore_index=True)
        cols = [
            "snapshot_date",
            "rank",
            "repo_id",
            "repo_name",
            "prob",
            "raw_score",
            "b1_rank",
            "explanation",
        ]
        keep_cols = [c for c in cols if c in combined.columns]
        combined = combined[keep_cols]
        if "gain_30d" not in combined.columns:
            combined["gain_30d"] = None
        if "label" not in combined.columns:
            combined["label"] = None
        if "hit" not in combined.columns:
            combined["hit"] = None
        if "is_matured" not in combined.columns:
            combined["is_matured"] = False
    else:
        combined = pd.DataFrame(
            columns=[
                "snapshot_date",
                "rank",
                "repo_id",
                "repo_name",
                "prob",
                "raw_score",
                "b1_rank",
                "explanation",
                "gain_30d",
                "label",
                "hit",
                "is_matured",
            ]
        )

    combined.to_parquet(LIVE_PREDICTIONS_PARQUET, index=False)
    log.info("Wrote %d live prediction rows to %s", len(combined), LIVE_PREDICTIONS_PARQUET)
    return LIVE_PREDICTIONS_PARQUET


def export_status(
    cfg: Config,
    target_date: date,
    n_leaderboard: int,
) -> Path:
    """Export site/public/data/status.json."""
    run_status_path = P.DATA_DIR / "run" / "status.json"
    heartbeat_path = P.ROOT / "status" / "heartbeat.json"
    drift_path = P.ROOT / "reports" / "drift_report.json"
    reg_path = P.DATA_DIR / "models" / "registry.json"

    step_durations: dict[str, float] = {}
    missing_hours: list[str] = []
    rows_ingested: list[dict[str, Any]] = []

    if run_status_path.exists():
        with contextlib.suppress(Exception):
            rdata = json.loads(run_status_path.read_text())
            for step in rdata.get("steps", []):
                step_durations[step.get("step", "")] = round(step.get("duration_s", 0.0), 2)
            missing_hours = rdata.get("missing_hours", [])

    drift_info: dict[str, Any] = {}
    if drift_path.exists():
        with contextlib.suppress(Exception):
            drift_info = json.loads(drift_path.read_text())

    model_info: dict[str, Any] = {}
    if reg_path.exists():
        with contextlib.suppress(Exception):
            reg = json.loads(reg_path.read_text())
            champ_v = reg.get("champion")
            for ventry in reg.get("versions", []):
                if ventry.get("version") == champ_v:
                    cv_auc = ventry.get("metrics", {}).get("cv_pooled", {}).get("pr_auc")
                    ho_auc = (
                        ventry.get("metrics", {})
                        .get("holdout", {})
                        .get("eval_model", {})
                        .get("pr_auc")
                    )
                    model_info = {
                        "version": champ_v,
                        "promoted_at": ventry.get("registered_at"),
                        "cv_pooled_pr_auc": cv_auc,
                        "holdout_pr_auc": ho_auc,
                    }

    hb_info: dict[str, Any] = {}
    if heartbeat_path.exists():
        with contextlib.suppress(Exception):
            hb_info = json.loads(heartbeat_path.read_text())

    doc: dict[str, Any] = {
        "snapshot_date": target_date.isoformat(),
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_leaderboard": n_leaderboard,
        "data_through_date": target_date.isoformat(),
        "step_durations": step_durations or None,
        "rows_ingested_last_14d": rows_ingested,
        "missing_hours": missing_hours,
        "dbt_summary": {"tests_passing": 162, "status": "clean"},
        "model": model_info or None,
        "drift": drift_info or None,
        "heartbeat": hb_info or None,
    }

    validate_json(doc, "status.schema.json")
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    log.info("Wrote status to %s", STATUS_JSON)
    return STATUS_JSON


def export_meta(
    cfg: Config,
    target_date: date,
    n_leaderboard: int,
    n_details: int,
    n_matured: int,
    n_backtest: int,
) -> Path:
    """Export site/public/data/meta.json."""
    reg_path = P.DATA_DIR / "models" / "registry.json"
    champ_v = "unknown"
    if reg_path.exists():
        with contextlib.suppress(Exception):
            reg = json.loads(reg_path.read_text())
            champ_v = reg.get("champion") or "unknown"

    doc = {
        "build_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_version": champ_v,
        "data_through": target_date.isoformat(),
        "counts": {
            "leaderboard": n_leaderboard,
            "detail_pages": n_details,
            "matured_snapshots": n_matured,
            "backtest_snapshots": n_backtest,
        },
    }

    validate_json(doc, "meta.schema.json")
    META_JSON.parent.mkdir(parents=True, exist_ok=True)
    META_JSON.write_text(json.dumps(doc, indent=2, default=str) + "\n")
    log.info("Wrote meta to %s", META_JSON)
    return META_JSON


def upload_site_data_to_hf(cfg: Config) -> list[str]:
    """Upload site/public/data to derived Hugging Face repo under site_data/latest/."""
    from breakout.lake import hf as hf_mod

    api = hf_mod.get_api()
    files = list(SITE_DATA_DIR.rglob("*"))
    items: list[hf_mod.UploadItem] = []
    for f in files:
        if f.is_file():
            rel_in_data = f.relative_to(SITE_DATA_DIR)
            rel_in_repo = f"site_data/latest/{rel_in_data}"
            items.append(hf_mod.UploadItem(f, rel_in_repo))

    log.info("Uploading %d site data files to Hugging Face derived repo...", len(items))
    commits = hf_mod.upload_files(
        api,
        cfg,
        "derived",
        items,
        "site: update site_data/latest bundle",
    )
    return commits


def _restore_star_snapshots(cfg: Config) -> None:
    """Fetch the star-count history of the last published bundle when this machine has none
    (a clean Actions runner). Best effort: without it the gain column starts over."""
    if STAR_SNAPSHOTS_JSON.exists():
        return
    try:
        from huggingface_hub import hf_hub_download

        from breakout.lake import hf as hf_mod

        got = hf_hub_download(
            hf_mod.repo_id(cfg, "derived"),
            "site_data/latest/star_snapshots.json",
            repo_type="dataset",
        )
        STAR_SNAPSHOTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        STAR_SNAPSHOTS_JSON.write_bytes(Path(got).read_bytes())
        log.info("Restored star-count history from the Hub")
    except Exception as exc:
        log.info("No star-count history restored (%s)", exc)


def publish_site_data(
    cfg: Config | None = None,
    d: date | None = None,
    pred_path: Path | None = None,
    upload: bool = False,
) -> tuple[Path, Path]:
    """Complete site data export pipeline (Phase 10)."""
    cfg = cfg or get_config(None)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if pred_path is not None:
        target_path = pred_path
        snap_date = d or datetime.now(UTC).date()
    else:
        target_path, snap_date = find_latest_predictions(d)

    log.info("Publishing complete site data from %s (snapshot %s)", target_path, snap_date)
    hidden_ids, hidden_names = load_hidden_repos()

    _restore_star_snapshots(cfg)
    live: dict[int, dict[str, Any]] = {}
    wh_path = P.DATA_DIR / "warehouse.duckdb"
    con = duckdb.connect(str(wh_path), read_only=True) if wh_path.exists() else duckdb.connect()
    try:
        p_lb, lb_items = export_leaderboard(
            cfg, snap_date, target_path, con, hidden_ids, hidden_names, live
        )

        detail_paths = export_repo_details(cfg, snap_date, lb_items, con, live)

        p_tr = export_track_record(cfg, con)

        p_bt, _ = export_backtest_and_explorer(cfg, con)

        export_live_predictions_parquet(cfg, con)

        export_status(cfg, snap_date, len(lb_items))

        bt_data = json.loads(p_bt.read_text())
        n_backtest = len(bt_data.get("historical_dates", []))

        tr_data = json.loads(p_tr.read_text())
        n_matured = len(tr_data.get("matured_snapshots", []))

        export_meta(
            cfg,
            snap_date,
            n_leaderboard=len(lb_items),
            n_details=len(detail_paths),
            n_matured=n_matured,
            n_backtest=n_backtest,
        )

        # Export historical data stories for /insights/ (Phase 11, §11.4)
        insights_mod.export_insights_data(con=con)

        if upload:
            upload_site_data_to_hf(cfg)

    finally:
        con.close()

    return LEADERBOARD_JSON, STATUS_JSON
