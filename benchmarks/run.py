"""DuckDB vs clickhouse-local on the same Parquet files (Phase 13.3).

    uv run python benchmarks/run.py --data ~/.cache/ghb-bench/data --clickhouse /path/to/clickhouse

The data directory holds one folder per event type (``WatchEvent``, ``IssueCommentEvent``,
``PullRequestEvent``) with the Parquet files of one year copied from the lake. For every query the
two dialects in ``benchmarks/sql/{duckdb,clickhouse}`` run once cold (the page cache of the data
files is dropped first) and ``--runs`` times warm. Each run is a fresh process, so the cold run
also pays the engine's start-up and metadata reads, and memory is measured per process.

Reported per query and engine: the in-engine time of every run, median and minimum of the warm
runs, the peak resident memory of the process, and whether the two engines returned identical
results. Results go to ``benchmarks/results.json``. Run it under a memory cap, for example
``systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 uv run python benchmarks/run.py``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SQL = HERE / "sql"
QUERIES = [
    ("q1_daily_stars", "Daily stars per repo (GROUP BY)"),
    ("q2_velocity_top100", "Top 100 by 7-day velocity on 12 dates (window functions)"),
    ("q3_sessions", "Sessionization, 30-minute gap (LAG + running sum)"),
    ("q4_cohort_retention", "Weekly stargazer cohort retention (join stars to later actions)"),
    ("q5_costar_overlap", "Co-star overlap of the 100 top repos (self-join on actor)"),
    ("q6a_distinct_exact", "Exact COUNT(DISTINCT actor_id) per month"),
    ("q6b_distinct_approx", "Approximate distinct count per month"),
]
ENGINES = ("duckdb", "clickhouse")


# -----------------------------------------------------------------------------
# child processes: run one query, print one JSON line
# -----------------------------------------------------------------------------


def child_duckdb(sql_file: Path, data: Path, threads: int, memory_gb: float, tmp: Path) -> None:
    import duckdb

    sql = sql_file.read_text().replace("{DATA}", str(data))
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}")
    con.execute(f"SET memory_limit = '{memory_gb}GB'")
    con.execute(f"SET temp_directory = '{tmp}'")
    t0 = time.perf_counter()
    cur = con.execute(sql)
    rows = cur.fetchall()
    elapsed = time.perf_counter() - t0
    cols = [d[0] for d in cur.description]
    print(
        json.dumps(
            {"elapsed_s": elapsed, "columns": cols, "rows": [list(map(_norm, r)) for r in rows]}
        )
    )


def _norm(v: Any) -> str:
    """One string form for a value so that results of both engines can be compared."""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# -----------------------------------------------------------------------------
# parent
# -----------------------------------------------------------------------------


def drop_cache(data: Path) -> int:
    """Evict the data files from the OS page cache (no root needed for clean pages)."""
    n = 0
    for f in data.rglob("*.parquet"):
        fd = os.open(f, os.O_RDONLY)
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            n += 1
        finally:
            os.close(fd)
    return n


def run_child(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, str, float, int]:
    """Run ``cmd``: (returncode, stdout, stderr, wall seconds, peak RSS in MB of the child)."""
    out_f, err_f = cwd / "child.out", cwd / "child.err"
    t0 = time.perf_counter()
    with open(out_f, "w") as so, open(err_f, "w") as se:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=so, stderr=se)  # noqa: S603
        # wait4 reports the usage of this child alone (RUSAGE_CHILDREN is a running maximum)
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            if time.perf_counter() - t0 > timeout:
                p.kill()
                _, status, ru = os.wait4(p.pid, 0)
                return (
                    -9,
                    "",
                    f"timeout after {timeout}s",
                    time.perf_counter() - t0,
                    int(ru.ru_maxrss / 1024),
                )
            time.sleep(0.1)
    wall = time.perf_counter() - t0
    p.returncode = 0  # reaped above; Popen must not wait again
    return (
        os.waitstatus_to_exitcode(status),
        out_f.read_text(),
        err_f.read_text(),
        wall,
        int(ru.ru_maxrss / 1024),
    )


def run_once(engine: str, qname: str, a: argparse.Namespace, tmp: Path) -> dict[str, Any]:
    sql_file = SQL / engine / f"{qname}.sql"
    if engine == "duckdb":
        cmd = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--child",
            "--sql",
            str(sql_file),
            "--data",
            str(a.data),
            "--threads",
            str(a.threads),
            "--memory-gb",
            str(a.memory_gb),
            "--tmp",
            str(tmp),
        ]
    else:
        sql = sql_file.read_text().replace("{DATA}", str(a.data))
        budget = int(a.memory_gb * 2**30)
        spill = budget // 3
        cmd = [
            a.clickhouse,
            "local",
            "--time",
            "--format",
            "JSONCompactEachRow",
            "--output_format_json_quote_64bit_integers",
            "0",
            "--max_threads",
            str(a.threads),
            "--max_memory_usage",
            str(budget),
            "--max_bytes_before_external_group_by",
            str(spill),
            "--max_bytes_before_external_sort",
            str(spill),
            "--join_algorithm",
            "auto",
            "--query",
            sql,
        ]
    rc, out, err, wall, peak = run_child(cmd, tmp, a.timeout)
    res: dict[str, Any] = {"wall_s": round(wall, 3), "peak_rss_mb": peak, "ok": rc == 0}
    if rc != 0:
        res["error"] = err.strip()[-600:]
        return res
    if engine == "duckdb":
        doc = json.loads(out.strip().splitlines()[-1])
        res["elapsed_s"] = round(doc["elapsed_s"], 3)
        res["rows"] = doc["rows"]
    else:
        res["elapsed_s"] = round(float(err.strip().splitlines()[-1]), 3)
        res["rows"] = [[_norm(v) for v in json.loads(line)] for line in out.strip().splitlines()]
    return res


def same_results(a: list[list[str]], b: list[list[str]]) -> bool:
    return a == b


def approx_error(exact: list[list[str]], approx: list[list[str]]) -> dict[str, float]:
    errs = [abs(int(x[1]) - int(e[1])) / int(e[1]) for e, x in zip(exact, approx, strict=True)]
    return {"mean_rel_error": round(statistics.mean(errs), 5), "max_rel_error": round(max(errs), 5)}


def hardware() -> dict[str, Any]:
    cpuinfo = Path("/proc/cpuinfo").read_text().splitlines()
    cpu = next(
        (ln.split(":", 1)[1].strip() for ln in cpuinfo if ln.startswith("model name")),
        platform.processor(),
    )
    meminfo = Path("/proc/meminfo").read_text().splitlines()
    mem_kb = int(next(ln for ln in meminfo if ln.startswith("MemTotal")).split()[1])
    return {
        "cpu": cpu,
        "logical_cores": os.cpu_count(),
        "ram_gb": round(mem_kb / 1024 / 1024, 1),
        "os": platform.platform(),
    }


def engine_versions(clickhouse: str) -> dict[str, str]:
    import duckdb

    ch = subprocess.run([clickhouse, "local", "--version"], capture_output=True, text=True).stdout
    return {"duckdb": duckdb.__version__, "clickhouse_local": ch.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--clickhouse", default="clickhouse")
    ap.add_argument("--runs", type=int, default=5, help="warm runs after the cold one")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--memory-gb", type=float, default=4.0, help="engine memory limit")
    ap.add_argument("--timeout", type=int, default=1500, help="seconds per run")
    ap.add_argument("--only", default="", help="comma-separated query names or prefixes")
    ap.add_argument("--out", type=Path, default=HERE / "results.json")
    ap.add_argument("--tmp", type=Path, default=Path.home() / ".cache" / "ghb-bench" / "tmp")
    # internal
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--sql", type=Path)
    a = ap.parse_args()

    if a.child:
        child_duckdb(a.sql, a.data, a.threads, a.memory_gb, a.tmp)
        return 0

    a.tmp.mkdir(parents=True, exist_ok=True)
    wanted = [w for w in a.only.split(",") if w]
    queries = [q for q in QUERIES if not wanted or any(q[0].startswith(w) for w in wanted)]
    started = dt.datetime.now(dt.UTC)
    results: dict[str, Any] = {}
    prev = json.loads(a.out.read_text()) if a.out.exists() and wanted else {}
    prev_q = prev.get("queries", {})
    for qname, title in queries:
        entry: dict[str, Any] = {"title": title}
        first_rows: dict[str, list[list[str]]] = {}
        for engine in ENGINES:
            n = drop_cache(a.data)
            runs = []
            for i in range(1 + a.runs):
                r = run_once(engine, qname, a, a.tmp)
                r["kind"] = "cold" if i == 0 else "warm"
                if i == 0 and r["ok"]:
                    first_rows[engine] = r["rows"]
                r.pop("rows", None)
                runs.append(r)
                print(
                    f"{qname:22s} {engine:10s} {r['kind']:4s} "
                    f"{r.get('elapsed_s', 'FAILED')!s:>8} s  rss {r['peak_rss_mb']} MB"
                    + ("" if r["ok"] else f"  ERROR {r.get('error', '')[:120]}"),
                    flush=True,
                )
                if not r["ok"]:
                    break  # a failing query is reported once, not six times
            warm = [x["elapsed_s"] for x in runs if x["ok"] and x["kind"] == "warm"]
            cold = next((x["elapsed_s"] for x in runs if x["ok"] and x["kind"] == "cold"), None)
            entry[engine] = {
                "runs": runs,
                "cold_s": cold,
                "warm_median_s": round(statistics.median(warm), 3) if warm else None,
                "warm_min_s": round(min(warm), 3) if warm else None,
                "peak_rss_mb": max((x["peak_rss_mb"] for x in runs), default=0),
                "files_evicted_before": n,
                "completed": all(x["ok"] for x in runs),
            }
        d, c = first_rows.get("duckdb"), first_rows.get("clickhouse")
        if qname == "q6b_distinct_approx":
            exact = results.get("q6a_distinct_exact") or prev_q.get("q6a_distinct_exact")
            entry["results_identical"] = None  # estimates differ by design
            if d and c and exact and exact.get("exact_rows"):
                entry["duckdb"].update(approx_error(exact["exact_rows"], d))
                entry["clickhouse"].update(approx_error(exact["exact_rows"], c))
        else:
            entry["results_identical"] = (
                same_results(d, c) if d is not None and c is not None else None
            )
            entry["n_result_rows"] = len(d) if d is not None else None
            if qname == "q6a_distinct_exact":
                entry["exact_rows"] = d
        results[qname] = entry
    doc = {
        "generated_at": started.isoformat(timespec="seconds"),
        "hardware": hardware(),
        "versions": engine_versions(a.clickhouse),
        "settings": {
            "threads": a.threads,
            "engine_memory_limit_gb": a.memory_gb,
            "warm_runs": a.runs,
            "data": "one year (2022) of WatchEvent, IssueCommentEvent and PullRequestEvent, "
            "Parquet files of the lake",
        },
        "queries": {**prev_q, **results},
    }
    a.out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
