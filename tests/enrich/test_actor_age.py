from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pyarrow.parquet as pq

from breakout.config import load_config
from breakout.enrich import actor_age as A
from breakout.enrich import http as H


def _synthetic(n: int = 400, seed: int = 1):
    rng = np.random.default_rng(seed)
    ids = np.sort(rng.choice(np.arange(1_000, 200_000_000), size=n, replace=False))
    t0 = datetime(2008, 1, 1, tzinfo=UTC).timestamp()
    t1 = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    # monotone-ish truth with noise (ids are not perfectly ordered in time)
    base = t0 + (t1 - t0) * np.sqrt(ids / ids.max())
    noise = rng.normal(0, 20 * 86400, size=n)
    return ids, base + noise


def test_isotonic_is_monotone_and_lookup_is_asof() -> None:
    ids, y = _synthetic()
    fit = A.fit_isotonic(ids, y)
    assert np.all(np.diff(fit.epoch) >= 0)
    assert np.all(np.diff(fit.breakpoints) > 0)
    # lookup at an exact breakpoint, between breakpoints, and above the max
    assert fit.predict(np.array([fit.breakpoints[3]]))[0] == fit.epoch[3]
    mid = (fit.breakpoints[3] + fit.breakpoints[4]) // 2
    assert fit.predict(np.array([mid]))[0] == fit.epoch[3]
    assert fit.predict(np.array([fit.breakpoints[-1] + 10**9]))[0] == fit.epoch[-1]


def test_holdout_error_is_small_on_smooth_data() -> None:
    ids, y = _synthetic(800)
    rep = A.holdout_report(ids, y, 0.1)
    assert rep["n_holdout"] == 80
    assert rep["median_abs_err_days"] < 60
    assert len(rep["by_decile"]) == 10


def test_asof_sql_flags_extrapolation(tmp_path: Path) -> None:
    import pyarrow as pa

    p = tmp_path / "map.parquet"
    pq.write_table(
        pa.table(
            {
                "actor_id_breakpoint": pa.array([100, 1000, 5000], pa.int64()),
                "est_created_at": pa.array(
                    [datetime(2010, 1, 1), datetime(2015, 1, 1), datetime(2020, 1, 1)],
                    pa.timestamp("us"),
                ),
            }
        ),
        p,
    )
    con = duckdb.connect()
    con.execute("CREATE TABLE a(actor_id BIGINT)")
    con.execute("INSERT INTO a VALUES (5), (100), (999), (1000), (4999), (5000), (9999)")
    rows = con.execute(
        "SELECT * FROM ("
        + A.est_account_created_at(con, "a", p).sql_query()
        + ") ORDER BY actor_id"
    ).fetchall()
    got = {r[0]: (r[1].year, r[2]) for r in rows}
    assert got == {
        5: (2010, False),  # below min breakpoint -> first value
        100: (2010, False),
        999: (2010, False),
        1000: (2015, False),
        4999: (2015, False),
        5000: (2020, False),
        9999: (2020, True),
    }


def test_fetch_user_and_incremental_collect(tmp_path: Path, write_config) -> None:
    def mutate(d: dict) -> None:
        d["enrich"]["output_dir"] = str(tmp_path / "enrich")

    cfg = load_config(write_config(mutate))
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        uid = int(req.url.path.rsplit("/", 1)[1])
        if uid == 2:
            return httpx.Response(404, json={})
        return httpx.Response(
            200, json={"id": uid, "created_at": "2015-06-01T10:00:00Z", "type": "User"}
        )

    api = H.GitHubApi(
        "t", client=H.make_client("u", transport=httpx.MockTransport(handler)), clock=H.FakeClock()
    )
    out = A.collect_samples(cfg, api, [1, 2, 3])
    assert out == {"fetched": 3, "ok": 2, "total": 3}
    again = A.collect_samples(cfg, api, [1, 2, 3])
    assert again["fetched"] == 0 and len(calls) == 3  # incremental: nothing refetched
    by = {r["actor_id"]: r["status"] for r in A.load_samples(cfg)}
    assert by == {1: "ok", 2: "not_found", 3: "ok"}
