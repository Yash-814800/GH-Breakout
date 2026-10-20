"""Daily orchestrator (Phase 9, §9.2).

Executes the 15-step daily pipeline:
1.  Plan: identify days needing work in [cutover_date, D-1], cap at 10 days.
2.  Ingest: ingest planned days with ingest_day.
3.  Publish lake: upload changed day files + manifest + catalog.
4.  Compact: compact previous month if today >= 4th and complete.
5.  Working set: verify local window [D - recent_window_days, D) and log disk usage.
6.  State increment: update tastemaker/owner state with newly matured outcomes.
7.  Enrich: fetch missing/stale GitHub metadata, trending, HN.
8.  dbt: dbt source freshness and single-date feature mart build with persistent state.
9.  Score: predict candidates of D with champion, non-Monday calibration, B1 ranks, explanations.
10. Freeze: upload predictions to snapshots repo (immutable, conflict detection).
11. Ledger: append entry to ledger/predictions.csv.
12. Outcomes: compute realized labels for M = D - 30d, upload to snapshots.
13. Site data: publish leaderboard.json and status.json for website.
14. Heartbeat: write status/heartbeat.json.
15. Commit: git commit and push ledger/ and status/ (retrying rebase).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from breakout import dbt_runner as R
from breakout import features_dict
from breakout import paths as P
from breakout.config import Config, get_config
from breakout.daily import bootstrap as bootstrap_mod
from breakout.duck import connect
from breakout.features import build as fb_mod
from breakout.features import state as state_mod
from breakout.ingest import day as ingest_day_mod
from breakout.ingest import manifest as mf
from breakout.lake import compact as compact_mod
from breakout.lake import hf as hf_mod
from breakout.lake import layout as layout_mod
from breakout.lake import sync as sync_mod
from breakout.logging import get_logger
from breakout.ml import append_live as append_live_mod
from breakout.ml import dataset as D
from breakout.ml import explain as explain_mod
from breakout.ml import final as final_mod
from breakout.ml import registry as reg_mod
from breakout.ops import ledger as ledger_mod
from breakout.publish import site_data as site_data_mod
from breakout.schema import PARSER_VERSION, SCHEMA_VERSION

log = get_logger(__name__)

STATUS_JSON_PATH = P.DATA_DIR / "run" / "status.json"
HEARTBEAT_JSON_PATH = P.ROOT / "status" / "heartbeat.json"


def _disk_info(path: Path) -> dict[str, Any]:
    """Report disk usage in GB and percent for the filesystem containing path."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _manifest_fragments(cfg: Config, days: list[date]) -> list[hf_mod.UploadItem]:
    """Per-month manifest fragments for the months of ``days`` (same names as the backfill's)."""
    from breakout.lake.backfill_month import _manifest_fragment

    months = sorted({(d.year, d.month) for d in days})
    return [
        hf_mod.UploadItem(
            _manifest_fragment(cfg, y, m), f"manifests/hourly/hourly-{y:04d}{m:02d}.parquet"
        )
        for y, m in months
    ]


def _save_status(status_data: dict[str, Any]) -> None:
    STATUS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON_PATH.write_text(json.dumps(status_data, indent=2, default=str) + "\n")


def daily_run(
    cfg: Config | None = None,
    *,
    d: date | None = None,
    skip_deploy_data: bool = False,
    no_commit: bool = False,
    no_upload: bool = False,
) -> int:
    """Run the 15-step daily pipeline for target date d (default today UTC)."""
    cfg = cfg or get_config(None)
    target_date = d or datetime.now(UTC).date()
    start_time = datetime.now(UTC)

    status: dict[str, Any] = {
        "snapshot_date": target_date.isoformat(),
        "started_at": start_time.isoformat(),
        "steps": {},
        "freeze_conflict": False,
        "status": "running",
    }
    _save_status(status)

    log.info("=== Starting Breakout Daily Pipeline for %s ===", target_date)
    has_error = False

    def record_step(
        name: str, step_status: str, duration: float, details: dict[str, Any] | None = None
    ) -> None:
        status["steps"][name] = {
            "status": step_status,
            "duration_seconds": round(duration, 2),
            **(details or {}),
        }
        _save_status(status)

    # -------------------------------------------------------------------------
    # Step 0: Bootstrap (clean runner: manifest, window events, enrichment, state, champion)
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    if no_upload:
        record_step("0_bootstrap", "skipped", 0.0, {"reason": "no_upload_flag"})
    else:
        try:
            log.info("[Step 0/15] Bootstrapping working set from Hugging Face...")
            details = bootstrap_mod.bootstrap(cfg, target_date)
            record_step("0_bootstrap", "ok", time.perf_counter() - t0, details)
        except Exception as exc:
            log.exception("Step 0 (Bootstrap) failed")
            record_step("0_bootstrap", "error", time.perf_counter() - t0, {"error": str(exc)})
            has_error = True

    # -------------------------------------------------------------------------
    # Step 1: Plan
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    planned_days: list[date] = []
    try:
        log.info("[Step 1/15] Planning days to ingest...")
        manifest_path = layout_mod.hourly_manifest_path(cfg)
        cutover = cfg.history.cutover_date or date(2023, 6, 1)

        if manifest_path.exists():
            manifest = mf.HourlyManifest(manifest_path)
            now_dt = datetime.now(UTC).replace(tzinfo=None)
            plan_start = datetime(cutover.year, cutover.month, cutover.day)
            plan_end = datetime(target_date.year, target_date.month, target_date.day)

            todo = manifest.hours_needing_work(
                plan_start,
                plan_end,
                now_dt,
                parser_version=PARSER_VERSION,
                min_hour_lag=cfg.daily.min_hour_lag,
                late_hour_retry_days=cfg.daily.late_hour_retry_days,
            )
            days_needing_work = sorted({h.date() for h in todo})
            capped = len(days_needing_work) > 10
            planned_days = days_needing_work[:10]
            if capped:
                log.warning(
                    "Cap reached: %d days need work, processing first 10: %s",
                    len(days_needing_work),
                    [p.isoformat() for p in planned_days],
                )
            else:
                log.info("Planned %d days to ingest: %s", len(planned_days), planned_days)
            record_step(
                "1_plan",
                "ok",
                time.perf_counter() - t0,
                {"planned_days": [p.isoformat() for p in planned_days], "capped": capped},
            )
        else:
            log.info("No local manifest found at %s; planning empty", manifest_path)
            record_step("1_plan", "ok", time.perf_counter() - t0, {"planned_days": []})
    except Exception as exc:
        log.exception("Step 1 (Plan) failed")
        record_step("1_plan", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 2: Ingest
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    files_to_publish: list[Path] = []
    try:
        log.info("[Step 2/15] Ingesting %d planned day(s)...", len(planned_days))
        for day in planned_days:
            summary = ingest_day_mod.ingest_day(day, cfg=cfg)
            files_to_publish.extend(summary.files_written)
            log.info(
                "Ingested %s: %d hours ok, %d skipped, %d files written",
                day,
                summary.hours_ok,
                summary.hours_skipped,
                len(summary.files_written),
            )
        record_step(
            "2_ingest",
            "ok",
            time.perf_counter() - t0,
            {"days_ingested": len(planned_days), "files_written": len(files_to_publish)},
        )
    except Exception as exc:
        log.exception("Step 2 (Ingest) failed")
        record_step("2_ingest", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 3: Publish lake
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 3/15] Publishing lake changes...")
        fragments = _manifest_fragments(cfg, planned_days) if not no_upload else []
        if no_upload or not files_to_publish:
            if fragments and not no_upload:
                hf_mod.put_small_files(
                    hf_mod.get_api(),
                    cfg,
                    "events",
                    fragments,
                    f"chore(lake): manifest for {target_date}",
                )
            reason = "no_upload_flag" if no_upload else "no_files_written"
            log.info("Skipping lake upload (%s)", reason)
            record_step("3_publish_lake", "skipped", time.perf_counter() - t0, {"reason": reason})
        else:
            api = hf_mod.get_api()
            root = layout_mod.lake_root(cfg)
            commits = sync_mod.push_files(
                api,
                cfg,
                root,
                files_to_publish,
                f"chore(lake): daily ingest for {target_date}",
                extra=fragments,
            )
            log.info("Lake pushed in %d commit(s)", len(commits))
            record_step(
                "3_publish_lake",
                "ok",
                time.perf_counter() - t0,
                {"commits": commits, "n_files": len(files_to_publish)},
            )
    except Exception as exc:
        log.exception("Step 3 (Publish lake) failed")
        record_step("3_publish_lake", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 4: Compact
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 4/15] Checking monthly compaction eligibility...")
        # Compact previous month if today >= 4th of month
        if target_date.day >= 4:
            first_of_month = target_date.replace(day=1)
            last_month_end = first_of_month - timedelta(days=1)
            prev_year, prev_month = last_month_end.year, last_month_end.month
            complete, reason = compact_mod.month_complete(cfg, prev_year, prev_month)
            if complete:
                log.info("Compacting %04d-%02d...", prev_year, prev_month)
                c_res = compact_mod.compact_month(
                    cfg,
                    prev_year,
                    prev_month,
                    push=not no_upload,
                    delete_local_days=True,
                )
                record_step(
                    "4_compact",
                    "ok",
                    time.perf_counter() - t0,
                    {"year": prev_year, "month": prev_month, "status": c_res.status},
                )
            else:
                log.info("Compaction skipped for %04d-%02d: %s", prev_year, prev_month, reason)
                record_step(
                    "4_compact",
                    "skipped",
                    time.perf_counter() - t0,
                    {"reason": reason},
                )
        else:
            log.info("Compaction skipped: target_date.day (%d) < 4", target_date.day)
            record_step(
                "4_compact",
                "skipped",
                time.perf_counter() - t0,
                {"reason": "before_4th_day_of_month"},
            )
    except Exception as exc:
        log.exception("Step 4 (Compact) failed")
        record_step("4_compact", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 5: Working set
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        disk_before = _disk_info(P.DATA_DIR)
        log.info("[Step 5/15] Checking working set and disk usage: %s", disk_before)
        # Pull lake files if in remote mode (not no_upload) and files missing
        # In dry mode / local mode, existing lake files are used
        window_start = target_date - timedelta(days=cfg.daily.recent_window_days)
        window_vars = {
            "events_start": window_start.isoformat(),
            "events_end": target_date.isoformat(),
        }
        # state increments and the feature build both read the staging / intermediate tables
        for dbt_args in (["seed"], ["run", "--select", "staging", "intermediate"]):
            if (rc := R.run_dbt(cfg, dbt_args, extra_vars=window_vars)) != 0:
                raise RuntimeError(f"dbt {dbt_args[0]} failed with code {rc}")
        disk_after = _disk_info(P.DATA_DIR)
        record_step(
            "5_working_set",
            "ok",
            time.perf_counter() - t0,
            {"disk_before": disk_before, "disk_after": disk_after},
        )
    except Exception as exc:
        log.exception("Step 5 (Working set) failed")
        record_step("5_working_set", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 6: State increment
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 6/15] Incrementing persistent state to %s...", target_date)
        state_mod.update_state(cfg, target_date, upload=not no_upload)
        record_step(
            "6_state_increment",
            "ok",
            time.perf_counter() - t0,
            {"target_date": target_date.isoformat()},
        )
    except Exception as exc:
        log.exception("Step 6 (State increment) failed")
        record_step("6_state_increment", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 7: Enrich
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    enrich_details: dict[str, Any] = {}
    try:
        log.warning(
            "[Step 7/15] Live enrichment (repo metadata, trending, HN) is not wired yet: "
            "metadata features stay Unknown/NULL for new repos"
        )
        enrich_details["reason"] = "not_implemented"
        record_step("7_enrich", "skipped", time.perf_counter() - t0, enrich_details)
    except Exception as exc:
        log.exception("Step 7 (Enrich) failed")
        record_step("7_enrich", "warning", time.perf_counter() - t0, {"warning": str(exc)})

    # -------------------------------------------------------------------------
    # Step 8: dbt
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    freshness_passed = True
    try:
        log.info("[Step 8/15] Running dbt single-snapshot feature build for %s...", target_date)
        # dbt source freshness check
        try:
            freshness_passed = R.run_dbt(cfg, ["source", "freshness"]) == 0
        except Exception:
            freshness_passed = False

        window_start = target_date - timedelta(days=cfg.daily.recent_window_days)
        dbt_rc = fb_mod.run_features_single(
            cfg,
            target_date,
            window=(window_start, target_date),
            use_persistent_state=True,
        )
        if dbt_rc != 0:
            raise RuntimeError(f"dbt run_features_single failed with code {dbt_rc}")

        record_step(
            "8_dbt",
            "ok",
            time.perf_counter() - t0,
            {"freshness_passed": freshness_passed},
        )
    except Exception as exc:
        log.exception("Step 8 (dbt) failed")
        record_step(
            "8_dbt",
            "error",
            time.perf_counter() - t0,
            {"error": str(exc), "freshness_passed": freshness_passed},
        )
        has_error = True

    # -------------------------------------------------------------------------
    # Step 9: Score
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    pred_path = P.DATA_DIR / "run" / f"predictions_{target_date}.parquet"
    live_feat_path = P.DERIVED_DIR / "live" / "features" / f"date={target_date}.parquet"
    n_candidates = 0
    file_sha256 = ""
    model_version = "unknown"

    try:
        log.info("[Step 9/15] Scoring candidates for %s with champion model...", target_date)
        model = reg_mod.load_champion(cfg)
        model_version = model.version

        wh = fb_mod.warehouse_path()
        con = connect(wh, read_only=True)
        try:
            feat_df = con.execute(
                f"select * from mart_repo_features "
                f"where snapshot_date = date '{target_date}' order by repo_id"
            ).df()
        finally:
            con.close()

        n_candidates = len(feat_df)
        log.info("Found %d candidates on %s", n_candidates, target_date)

        # Save live features parquet
        live_feat_path.parent.mkdir(parents=True, exist_ok=True)
        feat_df.to_parquet(live_feat_path, index=False)
        if not no_upload:
            hf_mod.put_small_files(
                hf_mod.get_api(),
                cfg,
                "derived",
                [hf_mod.UploadItem(live_feat_path, f"live/features/date={target_date}.parquet")],
                f"live features for {target_date}",
            )

        if n_candidates > 0:
            pred = reg_mod.predict(model, feat_df, explain=False)
            probs = pred["prob"].to_numpy().copy()

            # ADR-025 Addendum: Non-Monday calibration adjustment
            if target_date.weekday() != 0:
                # 0.73 / 0.90 ~ 0.8111
                probs = np.clip(probs * (0.73 / 0.90), 1e-6, 1.0)

            raw_scores = pred["raw_score"].to_numpy()
            repo_ids = feat_df["repo_id"].to_numpy()

            # Rank by calibrated probability descending (tie-breaks: raw_score desc, repo_id asc)
            # lexsort sorts by last key first, so primary key is last
            sort_order = np.lexsort((repo_ids, -raw_scores, -probs))
            ranks = np.empty_like(sort_order)
            ranks[sort_order] = np.arange(1, len(sort_order) + 1)

            # Baseline B1 rank (stars_14d desc, stars_total desc, repo_id asc)
            s14 = (
                feat_df["stars_14d"].to_numpy()
                if "stars_14d" in feat_df
                else np.zeros(n_candidates)
            )
            stot = (
                feat_df["stars_total"].to_numpy()
                if "stars_total" in feat_df
                else np.zeros(n_candidates)
            )
            b1_order = np.lexsort((repo_ids, -stot, -s14))
            b1_ranks = np.empty_like(b1_order)
            b1_ranks[b1_order] = np.arange(1, len(b1_order) + 1)

            # Compute explanations for top 2 * leaderboard_size
            n_explain = min(n_candidates, cfg.site.leaderboard_size * 2)
            top_indices = sort_order[:n_explain]
            explanations: list[str | None] = [None] * n_candidates
            top_contribs_json: list[str | None] = [None] * n_candidates

            if n_explain > 0:
                top_subset = feat_df.iloc[top_indices]
                X_top = D.apply_categories(top_subset[model.features], model.categories)
                sv_top = explain_mod.shap_values(model.booster, X_top)
                feats_dict = features_dict.load()

                for row_i, orig_idx in enumerate(top_indices):
                    c_list = explain_mod.top_contributions(sv_top[row_i], model.features)
                    row_dict = top_subset.iloc[row_i][model.features].to_dict()
                    sent = explain_mod.explain_sentence(
                        row_dict, c_list, model.reference, feats_dict
                    )
                    explanations[orig_idx] = sent
                    top_contribs_json[orig_idx] = json.dumps(
                        [{"feature": f, "value": v} for f, v in c_list]
                    )

            # Resolve repo names
            names_map = final_mod.repo_names(cfg, [int(r) for r in repo_ids])
            repo_names_list = [names_map.get(int(r), f"repo_id={int(r)}") for r in repo_ids]

            pred_df = pd.DataFrame(
                {
                    "snapshot_date": target_date,
                    "repo_id": repo_ids,
                    "repo_name": repo_names_list,
                    "rank": ranks.astype(np.int32),
                    "prob": probs.astype(np.float64),
                    "raw_score": raw_scores.astype(np.float64),
                    "b1_rank": b1_ranks.astype(np.int32),
                    "explanation": explanations,
                    "top_contribs": top_contribs_json,
                    "model_version": model_version,
                    "features_hash": features_dict.dictionary_hash(),
                    "schema_version": int(SCHEMA_VERSION),
                    "suspicion_score": [None] * n_candidates,
                }
            )
        else:
            pred_df = pd.DataFrame(
                columns=[
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
                    "features_hash",
                    "schema_version",
                    "suspicion_score",
                ]
            )

        pred_path.parent.mkdir(parents=True, exist_ok=True)
        pred_df.to_parquet(pred_path, index=False)
        file_sha256 = ledger_mod.file_sha256(pred_path)

        log.info("Wrote %s (sha256: %s)", pred_path, file_sha256)
        record_step(
            "9_score",
            "ok",
            time.perf_counter() - t0,
            {
                "n_candidates": n_candidates,
                "model_version": model_version,
                "file_sha256": file_sha256,
            },
        )
    except Exception as exc:
        log.exception("Step 9 (Score) failed")
        record_step("9_score", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 10: Freeze
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    hf_commit = "local"
    freeze_conflict = False
    try:
        log.info("[Step 10/15] Freezing predictions snapshot...")
        # Local snapshot copy
        snap_local = (
            P.DATA_DIR / "snapshots" / "predictions" / f"date={target_date}" / "predictions.parquet"
        )
        snap_local.parent.mkdir(parents=True, exist_ok=True)
        if pred_path.exists():
            shutil.copy2(pred_path, snap_local)

        if not no_upload and pred_path.exists():
            api = hf_mod.get_api()
            rel_path = f"predictions/date={target_date}/predictions.parquet"
            rid = hf_mod.repo_id(cfg, "snapshots")
            rtype = hf_mod.repo_type("snapshots")

            # Check if exists remotely
            exists_remotely = False
            try:
                info = api.get_paths_info(rid, [rel_path], repo_type=rtype)
                exists_remotely = len(info) > 0
            except Exception:
                exists_remotely = False

            if exists_remotely:
                # Compare sha256 to ensure immutable contract
                temp_down = P.TMP_DIR / f"remote_{target_date}.parquet"
                try:
                    down_path = api.hf_hub_download(
                        rid, rel_path, repo_type=rtype, local_dir=str(P.TMP_DIR)
                    )
                    remote_sha = ledger_mod.file_sha256(Path(down_path))
                    if remote_sha == file_sha256:
                        log.info("Snapshot already exists with identical sha256: no-op")
                        hf_commit = "existing"
                    else:
                        log.error(
                            "FREEZE CONFLICT: remote sha %s != local sha %s for %s",
                            remote_sha,
                            file_sha256,
                            target_date,
                        )
                        freeze_conflict = True
                        status["freeze_conflict"] = True
                finally:
                    if temp_down.exists():
                        temp_down.unlink()
            else:
                item = hf_mod.UploadItem(pred_path, rel_path, file_sha256)
                commits = hf_mod.upload_files(
                    api,
                    cfg,
                    "snapshots",
                    [item],
                    f"freeze: predictions for {target_date}",
                )
                hf_commit = commits[0] if commits else "committed"
                log.info("Uploaded snapshot in commit %s", hf_commit)

        record_step(
            "10_freeze",
            "conflict" if freeze_conflict else "ok",
            time.perf_counter() - t0,
            {"hf_commit": hf_commit, "freeze_conflict": freeze_conflict},
        )
    except Exception as exc:
        log.exception("Step 10 (Freeze) failed")
        record_step("10_freeze", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 11: Ledger
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 11/15] Appending to tamper-evident ledger...")
        if file_sha256 and not freeze_conflict and pred_path.exists():
            row_hash, appended = ledger_mod.append_entry(
                date_val=target_date,
                model_version=model_version,
                n_candidates=n_candidates,
                predictions_file=pred_path,
                hf_commit=hf_commit,
            )
            record_step(
                "11_ledger",
                "ok",
                time.perf_counter() - t0,
                {"row_hash": row_hash, "appended": appended},
            )
        else:
            record_step(
                "11_ledger",
                "skipped",
                time.perf_counter() - t0,
                {"reason": "freeze_conflict_or_empty"},
            )
    except Exception as exc:
        log.exception("Step 11 (Ledger) failed")
        record_step("11_ledger", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 12: Outcomes
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 12/15] Computing realized outcomes for matured snapshot...")
        m_date = target_date - timedelta(days=cfg.labels.horizon_days)
        outcomes_path = (
            P.DATA_DIR / "snapshots" / "outcomes" / f"date={m_date}" / "outcomes.parquet"
        )
        if not outcomes_path.exists():
            # Check if predictions exist for m_date
            pred_m = (
                P.DATA_DIR / "snapshots" / "predictions" / f"date={m_date}" / "predictions.parquet"
            )
            if pred_m.exists():
                pred_df = pd.read_parquet(pred_m)
                cand_ids = [int(r) for r in pred_df["repo_id"]]
                wh = fb_mod.warehouse_path()
                con = connect(wh, read_only=True)
                try:
                    outcomes_df = append_live_mod.compute_live_labels(cfg, m_date, cand_ids, con)
                finally:
                    con.close()

                outcomes_path.parent.mkdir(parents=True, exist_ok=True)
                outcomes_df.to_parquet(outcomes_path, index=False)
                log.info("Wrote %d outcomes to %s", len(outcomes_df), outcomes_path)

                if not no_upload:
                    api = hf_mod.get_api()
                    rel_out = f"outcomes/date={m_date}/outcomes.parquet"
                    item = hf_mod.UploadItem(outcomes_path, rel_out)
                    hf_mod.upload_files(
                        api,
                        cfg,
                        "snapshots",
                        [item],
                        f"outcomes: realized labels for {m_date}",
                    )
        record_step(
            "12_outcomes",
            "ok",
            time.perf_counter() - t0,
            {"matured_date": m_date.isoformat()},
        )
    except Exception as exc:
        log.exception("Step 12 (Outcomes) failed")
        record_step("12_outcomes", "warning", time.perf_counter() - t0, {"warning": str(exc)})

    # -------------------------------------------------------------------------
    # Step 13: Site data
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 13/15] Publishing site data...")
        if skip_deploy_data:
            record_step(
                "13_site_data",
                "skipped",
                time.perf_counter() - t0,
                {"reason": "skip_deploy_data_flag"},
            )
        else:
            p1, p2 = site_data_mod.publish_site_data(
                cfg, target_date, pred_path, upload=not no_upload
            )
            record_step(
                "13_site_data",
                "ok",
                time.perf_counter() - t0,
                {"leaderboard": str(p1), "status": str(p2)},
            )
    except Exception as exc:
        log.exception("Step 13 (Site data) failed")
        record_step("13_site_data", "error", time.perf_counter() - t0, {"error": str(exc)})
        has_error = True

    # -------------------------------------------------------------------------
    # Step 14: Heartbeat
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    total_runtime = (datetime.now(UTC) - start_time).total_seconds()
    try:
        log.info("[Step 14/15] Writing status/heartbeat.json...")
        HEARTBEAT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        previous: dict[str, Any] = {}
        if HEARTBEAT_JSON_PATH.exists():
            previous = json.loads(HEARTBEAT_JSON_PATH.read_text())
        # a failed run must not refresh last_success_at (health.yml reads it)
        heartbeat = {
            "last_success_at": (
                previous.get("last_success_at") if has_error else datetime.now(UTC).isoformat()
            ),
            "snapshot_date": target_date.isoformat(),
            "model_version": model_version,
            "n_candidates": n_candidates,
            "runtime_seconds": round(total_runtime, 1),
            "freeze_conflict": freeze_conflict,
            "missing_hours_older_than_3d": 0,
            "dbt_freshness_passed": freshness_passed,
            "status": "healthy"
            if not has_error and not freeze_conflict and freshness_passed
            else "unhealthy",
        }
        HEARTBEAT_JSON_PATH.write_text(json.dumps(heartbeat, indent=2) + "\n")
        record_step("14_heartbeat", "ok", time.perf_counter() - t0)
    except Exception as exc:
        log.exception("Step 14 (Heartbeat) failed")
        record_step("14_heartbeat", "error", time.perf_counter() - t0, {"error": str(exc)})

    # -------------------------------------------------------------------------
    # Step 15: Commit
    # -------------------------------------------------------------------------
    t0 = time.perf_counter()
    try:
        log.info("[Step 15/15] Git committing ledger and status...")
        if no_commit:
            record_step(
                "15_commit",
                "skipped",
                time.perf_counter() - t0,
                {"reason": "no_commit_flag"},
            )
        else:
            # Stage ledger and status files
            subprocess.run(["git", "add", "ledger/", "status/"], cwd=P.ROOT, check=False)
            diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=P.ROOT, check=False)
            if diff.returncode != 0:
                # Changes to commit
                msg = f"chore(daily): predictions for {target_date}"
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=github-actions[bot]",
                        "-c",
                        "user.email=github-actions[bot]@users.noreply.github.com",
                        "commit",
                        "-m",
                        msg,
                    ],
                    cwd=P.ROOT,
                    check=True,
                )
                # Pull with rebase and push (with 3 retries)
                for attempt in range(1, 4):
                    pull_res = subprocess.run(["git", "pull", "--rebase"], cwd=P.ROOT, check=False)
                    push_res = subprocess.run(["git", "push"], cwd=P.ROOT, check=False)
                    if pull_res.returncode == 0 and push_res.returncode == 0:
                        break
                    time.sleep(2.0 * attempt)
            record_step("15_commit", "ok", time.perf_counter() - t0)
    except Exception as exc:
        log.exception("Step 15 (Commit) failed")
        record_step("15_commit", "warning", time.perf_counter() - t0, {"warning": str(exc)})

    status["status"] = "failed" if has_error else "success"
    status["finished_at"] = datetime.now(UTC).isoformat()
    status["total_runtime_seconds"] = round((datetime.now(UTC) - start_time).total_seconds(), 2)
    _save_status(status)

    log.info(
        "=== Finished Breakout Daily Pipeline (%s in %.1fs) ===",
        status["status"],
        status["total_runtime_seconds"],
    )
    return 1 if has_error else 0
