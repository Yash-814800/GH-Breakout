"""Turn benchmarks/results.json into the results table (Markdown) and a chart (PNG).

    uv run python benchmarks/report.py

Writes benchmarks/results.md and docs/blog/img/duckdb-vs-clickhouse.png.

Every query is reported, including the ones where an engine is slower or did not finish.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results.json"
OUT_MD = HERE / "results.md"
OUT_PNG = ROOT / "docs" / "blog" / "img" / "duckdb-vs-clickhouse.png"
SHORT = {
    "q1_daily_stars": "Q1 daily stars",
    "q2_velocity_top100": "Q2 7-day velocity, top 100",
    "q3_sessions": "Q3 sessionization",
    "q4_cohort_retention": "Q4 cohort retention",
    "q5_costar_overlap": "Q5 co-star overlap",
    "q6a_distinct_exact": "Q6a exact distinct",
    "q6b_distinct_approx": "Q6b approx distinct",
}
DUCK, CH = "#4650c4", "#d99a0b"


def _s(v: float | None) -> str:
    return "did not finish" if v is None else f"{v:.2f}"


def _ratio(a: float | None, b: float | None) -> str:
    if a is None or b is None or a == 0:
        return "-"
    r = b / a
    return f"{r:.1f}x slower" if r >= 1 else f"{1 / r:.1f}x faster"


def table(doc: dict) -> str:
    L = [
        "| Query | DuckDB median / min (s) | ClickHouse median / min (s) | ClickHouse vs DuckDB "
        "(median) | Peak memory DuckDB / ClickHouse (MB) | Same result |",
        "|---|---|---|---|---|---|",
    ]
    for q, r in doc["queries"].items():
        d, c = r["duckdb"], r["clickhouse"]
        if q == "q6b_distinct_approx":
            same = "estimate"
        elif not (d["completed"] and c["completed"]):
            same = "n/a"
        else:
            same = {True: "yes", False: "**NO**", None: "n/a"}[r.get("results_identical")]
        L.append(
            f"| {SHORT.get(q, q)} | {_s(d['warm_median_s'])} / {_s(d['warm_min_s'])} | "
            f"{_s(c['warm_median_s'])} / {_s(c['warm_min_s'])} | "
            f"{_ratio(d['warm_median_s'], c['warm_median_s'])} | "
            f"{d['peak_rss_mb']} / {c['peak_rss_mb']} | {same} |"
        )
    L += [
        "",
        "Cold run (first run after dropping the data files from the page cache), seconds:",
        "",
    ]
    L += ["| Query | DuckDB cold | ClickHouse cold |", "|---|---|---|"]
    for q, r in doc["queries"].items():
        L.append(
            f"| {SHORT.get(q, q)} | {_s(r['duckdb']['cold_s'])} | {_s(r['clickhouse']['cold_s'])} |"
        )
    hi = HERE / "results_highmem.json"
    if hi.exists():
        h = json.loads(hi.read_text())
        lim = h["settings"]["engine_memory_limit_gb"]
        L += [
            "",
            f"Queries that did not finish at 4 GB, repeated with a {lim} GB engine memory limit "
            "(same data, threads and method), seconds:",
            "",
            "| Query | DuckDB median / min | ClickHouse median / min | ClickHouse vs DuckDB "
            "| Peak memory DuckDB / ClickHouse (MB) | Same result |",
            "|---|---|---|---|---|---|",
        ]
        for q, r in h["queries"].items():
            d, c = r["duckdb"], r["clickhouse"]
            same = (
                "n/a"
                if not (d["completed"] and c["completed"])
                else {True: "yes", False: "**NO**", None: "n/a"}[r.get("results_identical")]
            )
            L.append(
                f"| {SHORT.get(q, q)} | {_s(d['warm_median_s'])} / {_s(d['warm_min_s'])} | "
                f"{_s(c['warm_median_s'])} / {_s(c['warm_min_s'])} | "
                f"{_ratio(d['warm_median_s'], c['warm_median_s'])} | "
                f"{d['peak_rss_mb']} / {c['peak_rss_mb']} | {same} |"
            )
    q6b = doc["queries"].get("q6b_distinct_approx", {})
    if "mean_rel_error" in q6b.get("duckdb", {}):
        L += [
            "",
            "Approximate distinct count, error against the exact count (12 months): "
            f"DuckDB mean {q6b['duckdb']['mean_rel_error']:.2%}, "
            f"max {q6b['duckdb']['max_rel_error']:.2%}; "
            f"ClickHouse mean {q6b['clickhouse']['mean_rel_error']:.2%}, "
            f"max {q6b['clickhouse']['max_rel_error']:.2%}.",
        ]
    return "\n".join(L) + "\n"


def chart(doc: dict) -> None:
    qs = list(doc["queries"])
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=110)
    y = range(len(qs))
    h = 0.38
    d = [doc["queries"][q]["duckdb"]["warm_median_s"] or 0 for q in qs]
    c = [doc["queries"][q]["clickhouse"]["warm_median_s"] or 0 for q in qs]
    ax.barh([i - h / 2 for i in y], d, h, color=DUCK, label="DuckDB")
    ax.barh([i + h / 2 for i in y], c, h, color=CH, label="clickhouse-local")
    for i, (a, b) in enumerate(zip(d, c, strict=True)):
        ax.text(a, i - h / 2, f" {a:.1f}" if a else " n/a", va="center", fontsize=8)
        ax.text(b, i + h / 2, f" {b:.1f}" if b else " n/a", va="center", fontsize=8)
    ax.set_yticks(list(y), [SHORT.get(q, q) for q in qs], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Median of 5 warm runs, seconds (lower is better)")
    ax.set_title("DuckDB vs clickhouse-local on the same Parquet files (one year of GitHub events)")
    ax.legend(frameon=False, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG)


def main() -> None:
    doc = json.loads(RESULTS.read_text())
    OUT_MD.write_text(table(doc))
    chart(doc)
    print(f"wrote {OUT_MD} and {OUT_PNG}")


if __name__ == "__main__":
    main()
