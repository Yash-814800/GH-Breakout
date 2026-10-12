"""Star-capture quality report: WatchEvent (and total) per day vs. a healthy-year baseline.

``ratio_*`` columns compare each day with the median of the same weekday in the baseline year.
``watch_per_issue`` is a seasonality-robust cross-check: stars relative to IssuesEvent, which the
2025-26 degradation did not affect.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

BASELINE_YEAR = 2024


def build_table(source: Path, baseline_year: int = BASELINE_YEAR) -> list[dict]:
    """Daily rows with ratios. ``source`` is parquet with day,total,watch,fork,issues,pr columns."""
    con = duckdb.connect()
    rows = con.execute(
        f"""
        WITH d AS (
            SELECT CAST(day AS DATE) AS day, total, watch, issues, fork, pr,
                   dayofweek(CAST(day AS DATE)) AS dow
            FROM read_parquet(?)
        ),
        base AS (
            SELECT dow, median(watch) AS watch_med, median(total) AS total_med,
                   median(watch * 1.0 / nullif(issues, 0)) AS wpi_med
            FROM d WHERE year(day) = {int(baseline_year)} GROUP BY dow
        )
        SELECT d.day, d.total, d.watch, d.fork, d.issues, d.pr,
               d.watch / base.watch_med AS ratio_watch,
               d.total / base.total_med AS ratio_total,
               (d.watch * 1.0 / nullif(d.issues, 0)) / base.wpi_med AS ratio_watch_per_issue
        FROM d JOIN base USING (dow) ORDER BY d.day
        """,
        [str(source)],
    ).fetchall()
    cols = [
        "day",
        "total",
        "watch",
        "fork",
        "issues",
        "pr",
        "ratio_watch",
        "ratio_total",
        "ratio_watch_per_issue",
    ]
    return [dict(zip(cols, r, strict=True)) for r in rows]


def monthly(rows: list[dict]) -> list[dict]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["day"].strftime("%Y-%m"), []).append(r)
    res = []
    for month, rs in out.items():

        def med(key: str, rs: list[dict] = rs) -> float:
            v = sorted(x[key] for x in rs if x[key] is not None)
            return v[len(v) // 2] if v else float("nan")

        res.append(
            {
                "month": month,
                "days": len(rs),
                "watch_per_day": sum(x["watch"] for x in rs) / len(rs),
                "ratio_watch": med("ratio_watch"),
                "ratio_total": med("ratio_total"),
                "ratio_wpi": med("ratio_watch_per_issue"),
            }
        )
    return res


def first_sustained_drop(
    rows: list[dict], key: str, threshold: float, run: int = 14
) -> date | None:
    """First day starting ``run`` consecutive days all below ``threshold`` (after the baseline)."""
    streak = 0
    for i, r in enumerate(rows):
        if r["day"].year > BASELINE_YEAR and r[key] is not None and r[key] < threshold:
            streak += 1
            if streak == run:
                return rows[i - run + 1]["day"]
        else:
            streak = 0
    return None


def plot(
    rows: list[dict],
    months: list[dict],
    out_png: Path,
    trusted_end: date,
    degraded_end: date | None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    days = [r["day"] for r in rows]
    fig, ax = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True, constrained_layout=True)
    ax[0].plot(days, [r["watch"] for r in rows], lw=0.8, color="#2563eb", label="WatchEvent / day")
    ax[0].set_ylabel("WatchEvents per day")
    ax[0].set_yscale("log")
    ax[1].plot(
        days,
        [r["ratio_watch"] for r in rows],
        lw=0.8,
        color="#2563eb",
        label="stars vs 2024 same-weekday median",
    )
    ax[1].plot(
        days,
        [r["ratio_watch_per_issue"] for r in rows],
        lw=0.8,
        color="#d97706",
        label="stars per IssuesEvent vs 2024",
    )
    ax[1].plot(
        days,
        [r["ratio_total"] for r in rows],
        lw=0.8,
        color="#6b7280",
        label="all events vs 2024 same-weekday median",
    )
    ax[1].axhline(1.0, color="#9ca3af", lw=0.6)
    ax[1].set_ylabel("ratio to 2024 baseline")
    ax[1].set_ylim(0, 2)
    for a in ax:
        a.axvline(trusted_end, color="#dc2626", ls="--", lw=1)
        a.axvspan(trusted_end, degraded_end or days[-1], color="#fecaca", alpha=0.35)
        if degraded_end:
            a.axvline(degraded_end, color="#16a34a", ls=":", lw=1)
        a.grid(alpha=0.25)
    ax[1].legend(loc="upper right", fontsize=8)
    ax[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax[0].set_title(
        "GH Archive star capture quality (red band = degraded era; dashed = trusted_end)"
    )
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def render_markdown(
    rows: list[dict],
    months: list[dict],
    *,
    png_rel: str,
    trusted_end: date,
    degraded_end: date | None,
    bytes_billed: int | None,
) -> str:
    w: list[str] = []
    add = w.append
    add("# GH Archive star-capture quality")
    add("")
    add(
        "Daily WatchEvent and total event counts from the public BigQuery dataset "
        "(`githubarchive.day.20*`, `type` column only"
        + (f", {bytes_billed / 1e9:.1f} GB billed" if bytes_billed else "")
        + f"), {rows[0]['day']} to {rows[-1]['day']}. Ratios compare each day with the median of "
        f"the same weekday in {BASELINE_YEAR}. Trusted era ends {trusted_end}"
        + (f"; degraded era ends {degraded_end}." if degraded_end else ".")
    )
    add("")
    add(f"![capture quality]({png_rel})")
    add("")
    add("## Where the stream degrades")
    add("")
    for key, label in (
        ("ratio_watch", "stars vs 2024 same-weekday median"),
        ("ratio_watch_per_issue", "stars per IssuesEvent vs 2024"),
    ):
        for thr in (0.8, 0.5, 0.2):
            d = first_sustained_drop(rows, key, thr)
            add(f"- first 14-day run with `{label}` < {thr:.0%}: **{d or 'never'}**")
    add("")
    add("## Monthly medians")
    add("")
    add(
        "| month | days | WatchEvents/day | stars ratio | stars/issue ratio | all-events ratio"
        " | era |"
    )
    add("|---|---:|---:|---:|---:|---:|---|")
    for m in months:
        y, mo = map(int, m["month"].split("-"))
        month_end = date(y + (mo == 12), mo % 12 + 1, 1)
        month_start = date(y, mo, 1)
        if month_end.toordinal() - 1 <= trusted_end.toordinal():
            era = "trusted"
        elif month_start > trusted_end:
            era = "degraded" if degraded_end is None or month_start <= degraded_end else "live"
        else:
            era = f"trusted to {trusted_end}, then degraded"
        add(
            f"| {m['month']} | {m['days']} | {m['watch_per_day']:,.0f} | {m['ratio_watch']:.2f} "
            f"| {m['ratio_wpi']:.2f} | {m['ratio_total']:.2f} | {era} |"
        )
    add("")
    add("<details><summary>Daily table</summary>")
    add("")
    add(
        "| day | total | watch | fork | issues | PR | stars ratio | stars/issue ratio | all ratio |"
    )
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:

        def f(x: float | None) -> str:
            return "" if x is None else f"{x:.2f}"

        add(
            f"| {r['day']} | {r['total']} | {r['watch']} | {r['fork']} | {r['issues']} | {r['pr']} "
            f"| {f(r['ratio_watch'])} | {f(r['ratio_watch_per_issue'])} | {f(r['ratio_total'])} |"
        )
    add("")
    add("</details>")
    add("")
    return "\n".join(w)
