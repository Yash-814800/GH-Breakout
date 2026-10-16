"""Actor-id -> account-creation-date map (phase 4.3).

GitHub user ids are assigned sequentially, so ``(id, created_at)`` pairs for ~3,000 real actor ids
are enough to estimate any account's age from its id with an isotonic fit and no per-actor calls.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.isotonic import IsotonicRegression

from breakout.config import Config
from breakout.enrich import names as names_mod
from breakout.enrich.common import (
    atomic_copy_parquet,
    connect_limited,
    enrich_dir,
    sql_file_list,
    sql_str,
    staging_dir,
)
from breakout.enrich.http import GitHubApi
from breakout.lake import layout
from breakout.logging import get_logger

log = get_logger(__name__)

SAMPLES = "actor_age_samples.parquet"
AGE_MAP = "actor_id_age_map.parquet"
PER_MONTH_SAMPLE = 20_000

SAMPLE_SCHEMA = pa.schema(
    [
        ("actor_id", pa.int64()),
        ("status", pa.string()),  # ok | not_found | error
        ("created_at", pa.timestamp("us")),
        ("account_type", pa.string()),
        ("fetched_at", pa.timestamp("us")),
    ]
)

# Used by dbt/DuckDB: ``actors`` has ``actor_id``; the map is read from the parquet file.
ASOF_SQL = """
SELECT a.actor_id,
       coalesce(m.est_created_at,
                (SELECT min(est_created_at) FROM age_map)) AS est_account_created_at,
       a.actor_id > (SELECT max(actor_id_breakpoint) FROM age_map) AS est_is_extrapolated
FROM actors a
ASOF LEFT JOIN age_map m ON a.actor_id >= m.actor_id_breakpoint
"""


def pick_sample_ids(cfg: Config, n: int, *, per_month: int = PER_MONTH_SAMPLE) -> list[int]:
    """``n`` real actor ids at evenly spaced ranks of the sampled distinct-id distribution
    (always including the observed min and max)."""
    files = layout.glob_for("WatchEvent", None, None, cfg)
    if not files:
        raise FileNotFoundError("no WatchEvent files in the local lake")
    by_month: dict[str, list[Path]] = {}
    for f in files:
        by_month.setdefault(names_mod._month_of(f), []).append(f)
    stage = staging_dir(cfg, "actor_age")
    parts: list[Path] = []
    for month, mfiles in sorted(by_month.items()):
        out = stage / f"ids-{month}-{names_mod._signature(mfiles)}-{per_month}.parquet"
        parts.append(out)
        if out.exists():
            continue
        for stale in stage.glob(f"ids-{month}-*.parquet"):
            stale.unlink()
        con = connect_limited(stage / "tmp")
        try:
            atomic_copy_parquet(
                con,
                f"""SELECT DISTINCT actor_id FROM (
                      SELECT actor_id FROM read_parquet({sql_file_list(mfiles)},
                                                        hive_partitioning=false)
                      USING SAMPLE {per_month} ROWS (reservoir, 42))""",
                out,
            )
        finally:
            con.close()
        log.info("actor ids: sampled %s", month)
    con = connect_limited(stage / "tmp")
    try:
        con.execute(
            f"CREATE TEMP TABLE ids AS SELECT DISTINCT actor_id FROM "
            f"read_parquet({sql_file_list(parts)})"
        )
        total = con.execute("SELECT count(*) FROM ids").fetchone()[0]  # type: ignore[index]
        step = max(total // n, 1)
        rows = con.execute(
            f"""SELECT actor_id FROM (
                  SELECT actor_id, row_number() OVER (ORDER BY actor_id) - 1 AS rn FROM ids)
                WHERE rn % {step} = 0 OR rn = {total - 1}
                ORDER BY actor_id"""
        ).fetchall()
    finally:
        con.close()
    ids = [r[0] for r in rows]
    if len(ids) > n + 1:  # trim evenly, keeping first and last
        idx = np.linspace(0, len(ids) - 1, n).round().astype(int)
        ids = [ids[i] for i in sorted(set(idx.tolist()))]
    return ids


def _samples_path(cfg: Config) -> Path:
    return enrich_dir(cfg) / SAMPLES


def load_samples(cfg: Config) -> list[dict[str, Any]]:
    p = _samples_path(cfg)
    return pq.read_table(p).to_pylist() if p.exists() else []


def fetch_user(api: GitHubApi, actor_id: int, now: datetime) -> dict[str, Any]:
    r = api.rest_get(f"/user/{actor_id}")
    row: dict[str, Any] = {
        "actor_id": actor_id,
        "status": "error",
        "created_at": None,
        "account_type": None,
        "fetched_at": now,
    }
    if r.status_code == 404:
        row["status"] = "not_found"
    elif r.status_code == 200:
        body = r.json()
        if body.get("id") == actor_id and body.get("created_at"):
            row["status"] = "ok"
            row["created_at"] = (
                datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            row["account_type"] = body.get("type")
    else:
        log.warning("GET /user/%s -> HTTP %s", actor_id, r.status_code)
    return row


def save_samples(cfg: Config, rows: list[dict[str, Any]]) -> None:
    p = _samples_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    rows = sorted(rows, key=lambda r: r["actor_id"])
    pq.write_table(pa.Table.from_pylist(rows, schema=SAMPLE_SCHEMA), tmp, compression="zstd")
    tmp.replace(p)


def collect_samples(
    cfg: Config,
    api: GitHubApi,
    ids: list[int],
    *,
    save_every: int = 100,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, int]:
    """Fetch the ids that have no ok/not_found row yet (incremental); saves every N fetches."""
    rows = {r["actor_id"]: r for r in load_samples(cfg)}
    todo = [i for i in ids if i not in rows or rows[i]["status"] == "error"]
    log.info("actor-age: %d sampled ids, %d to fetch", len(ids), len(todo))
    for k, i in enumerate(todo, 1):
        rows[i] = fetch_user(api, i, datetime.now(UTC).replace(tzinfo=None))
        if k % save_every == 0:
            save_samples(cfg, list(rows.values()))
            log.info("actor-age: %d/%d fetched", k, len(todo))
        if should_stop():
            break
    save_samples(cfg, list(rows.values()))
    ok = sum(1 for r in rows.values() if r["status"] == "ok")
    return {"fetched": len(todo), "ok": ok, "total": len(rows)}


# ---- isotonic map ------------------------------------------------------------------------------


@dataclass
class Fit:
    breakpoints: np.ndarray  # actor ids, ascending, unique
    epoch: np.ndarray  # fitted created_at epoch seconds, non-decreasing

    def predict(self, actor_ids: np.ndarray) -> np.ndarray:
        """Step lookup (``ASOF``: value at the largest breakpoint <= id; below min -> first)."""
        idx = np.searchsorted(self.breakpoints, actor_ids, side="right") - 1
        return self.epoch[np.clip(idx, 0, None)]


def fit_isotonic(actor_ids: np.ndarray, created_epoch: np.ndarray) -> Fit:
    order = np.argsort(actor_ids)
    x, y = actor_ids[order].astype(float), created_epoch[order].astype(float)
    iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
    iso.fit(x, y)
    bx = np.asarray(iso.X_thresholds_, dtype=np.int64)
    by = np.asarray(iso.y_thresholds_, dtype=float)
    # one breakpoint per distinct id; drop ids whose fitted value equals the previous one
    keep = np.ones(len(bx), dtype=bool)
    keep[1:] = np.diff(by) != 0
    return Fit(bx[keep], by[keep])


def holdout_report(
    actor_ids: np.ndarray, created_epoch: np.ndarray, frac: float, seed: int = 20260416
) -> dict[str, Any]:
    """Fit on ``1 - frac`` of samples, report absolute error (days) on the hold-out."""
    rng = np.random.default_rng(seed)
    n = len(actor_ids)
    test = np.zeros(n, dtype=bool)
    test[rng.choice(n, size=max(int(n * frac), 1), replace=False)] = True
    fit = fit_isotonic(actor_ids[~test], created_epoch[~test])
    pred = fit.predict(actor_ids[test])
    err_days = np.abs(pred - created_epoch[test]) / 86400.0
    ids = actor_ids[test]
    deciles = np.quantile(actor_ids, np.linspace(0, 1, 11))
    by_dec = []
    for d in range(10):
        lo, hi = deciles[d], deciles[d + 1]
        m = (ids >= lo) & (ids <= hi if d == 9 else ids < hi)
        by_dec.append(
            {
                "decile": d + 1,
                "id_lo": int(lo),
                "id_hi": int(hi),
                "n": int(m.sum()),
                "median_abs_err_days": float(np.median(err_days[m])) if m.any() else None,
            }
        )
    return {
        "n_train": int((~test).sum()),
        "n_holdout": int(test.sum()),
        "median_abs_err_days": float(np.median(err_days)),
        "p90_abs_err_days": float(np.quantile(err_days, 0.9)),
        "by_decile": by_dec,
    }


def build_map(cfg: Config) -> dict[str, Any]:
    samples = [r for r in load_samples(cfg) if r["status"] == "ok"]
    if len(samples) < 50:
        raise RuntimeError(f"only {len(samples)} usable samples; run collect first")
    ids = np.array([r["actor_id"] for r in samples], dtype=np.int64)
    epoch = np.array(
        [r["created_at"].replace(tzinfo=UTC).timestamp() for r in samples], dtype=float
    )
    report = holdout_report(ids, epoch, cfg.enrich.actor_holdout_frac)
    fit = fit_isotonic(ids, epoch)
    table = pa.table(
        {
            "actor_id_breakpoint": pa.array(fit.breakpoints, pa.int64()),
            "est_created_at": pa.array(
                [datetime.fromtimestamp(float(e), UTC).replace(tzinfo=None) for e in fit.epoch],
                pa.timestamp("us"),
            ),
        }
    )
    dest = enrich_dir(cfg) / AGE_MAP
    tmp = dest.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(dest)
    report["breakpoints"] = len(fit.breakpoints)
    report["max_breakpoint_id"] = int(fit.breakpoints[-1])
    report["n_samples_ok"] = len(samples)
    return report


def est_account_created_at(con: Any, actors_table: str, age_map: str | Path) -> Any:
    """Relation with ``actor_id, est_account_created_at, est_is_extrapolated`` for every actor
    in ``actors_table`` (a table/view with ``actor_id``)."""
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW age_map AS SELECT * FROM read_parquet({sql_str(age_map)})"
    )
    con.execute(f"CREATE OR REPLACE TEMP VIEW actors AS SELECT actor_id FROM {actors_table}")
    return con.sql(ASOF_SQL)
