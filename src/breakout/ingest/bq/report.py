"""Render ``docs/bigquery_cost_plan.md`` (schedule per ADR-010)."""

from __future__ import annotations

from datetime import date


def gb(b: float) -> float:
    return b / 1e9


def render(
    survey: dict,
    dry: dict,
    *,
    cutover: date,
    trusted_end: date,
    budget: int,
    per_query_cap: int,
    spent_first: int,
    first_calendar_month: str,
    hourly_estimate: dict[str, float] | None,
    generated: date,
) -> str:
    months = dry["months"]
    total = dry["single_query_bytes"]
    w: list[str] = []
    add = w.append
    add("# BigQuery cost plan and backfill schedule (ADR-010)")
    add("")
    add(
        f"Generated {generated}. Supersedes the Phase 2 default and the earlier schedules in ADR-009. "
        f"**Approved split (human, 2026-10-12): BigQuery spine only for {dry['range'][0]}..{dry['range'][1]}; "
        f"everything from `history.cutover_date` = {cutover} comes from data.gharchive.org hourly files "
        "through the Phase 1 parser.** Nothing in the range below has been run; only dry runs."
    )
    add("")
    add("## 1. BigQuery spine, 2015-01..2023-05 (dry-run, to be approved before running)")
    add("")
    add(
        f"- Range: {dry['range'][0]} .. {dry['range'][1]} ({len(months)} calendar months), mode `spine`"
    )
    add(
        f"- Dry-run bytes, **one query over the whole range: {gb(total):,.1f} GB**; sum of the {len(months)} per-month queries: {gb(dry['sum_of_months_bytes']):,.1f} GB (identical: bytes are additive per table)"
    )
    add(
        f"- Monthly budget `bigquery.monthly_budget_bytes`: {gb(budget):,.0f} GB; already spent this calendar month ({first_calendar_month}): {gb(spent_first):,.1f} GB"
    )
    add(
        f"- **Fits in one calendar month:** {gb(spent_first + total):,.1f} GB of {gb(budget):,.0f} GB ({100 * (spent_first + total) / budget:.0f}%), leaving {gb(budget - spent_first - total):,.0f} GB headroom in {first_calendar_month}. No split across months needed."
    )
    biggest = max(months.items(), key=lambda kv: kv[1])
    add(
        f"- Per-query cap `per_query_max_bytes_billed` {gb(per_query_cap):,.0f} GB; largest month {biggest[0]} is {gb(biggest[1]):,.1f} GB, so 7-day chunks are far below it"
    )
    add(
        "- PushEvent rows ride in the same query (columns already scanned) and are aggregated into `push_daily` locally, so no separate push query is run"
    )
    gaps = dry["missing_day_tables"]
    add(
        f"- {len(gaps)} days have no `githubarchive.day` table ({', '.join(gaps)}). Probed 2026-10-12: "
        "2015-12-31, 2021-05-08, 2021-05-10, 2021-05-11 exist as hourly files (24/24 hours) and are listed in "
        "`history.hourly_gap_days` (fetched through the hourly parser although before the cutover); "
        "2020-08-22, 2021-08-26, 2021-10-26/27/28 exist in neither source nor in the month tables "
        "(checked, 1.5 GB scanned) and stay empty. 2021-08-27 and 2021-10-25 are partial days "
        "(80k and 58k events)"
    )
    add("")
    add("### Per-year bytes (GB scanned, spine)")
    add("")
    add("| year | GB |")
    add("|---|---:|")
    years = sorted({m[:4] for m in months})
    for y in years:
        add(f"| {y} | {gb(sum(v for m, v in months.items() if m.startswith(y))):,.1f} |")
    add(f"| **total** | **{gb(total):,.1f}** |")
    add("")
    add("## 2. Hourly files from the cutover onward (laptop, no BigQuery quota)")
    add("")
    add(
        f"- Order: trusted era {cutover}..{trusted_end} first, then the degraded era "
        f"the day after {trusted_end} .. last complete day (kept, flagged, never trained or "
        "evaluated on). Within an era oldest to newest."
    )
    add(
        "- `breakout backfill hourly [--dry]`: resumable through the hourly manifest (hours already `ok` at the current parser version are skipped), at most 4 concurrent downloads (`--workers`, default 2)."
    )
    if hourly_estimate:
        may_total = hourly_estimate.get("2025-05", 0)
        degraded = (
            sum(v for m, v in hourly_estimate.items() if "2025-06" <= m <= "2026-10") + may_total
        )
        trusted_months = sum(v for m, v in hourly_estimate.items() if "2023-06" <= m <= "2025-04")
        add(
            f"- Estimated download (sampled `Content-Length`, compressed): trusted era ~{gb(trusted_months):,.0f} GB (2023-06..2025-04) plus May 2025 up to the 23rd; degraded era ~{gb(degraded):,.0f} GB. Order of magnitude: **~2 TB total**."
        )
    add(
        "- Disk: day files are ZSTD parquet; staging is currently kept (about 2x the day file). A measured day is recorded in `docs/PROGRESS.md`. Plan on a few hundred GB with staging, or add staging cleanup after the day build before running the full range."
    )
    add("")
    add("## 3. Resulting coverage")
    add("")
    add("| period | source | detail_level | era |")
    add("|---|---|---|---|")
    add(
        f"| {dry['range'][0]} .. {dry['range'][1]} | BigQuery spine (`bq-YYYYMM.parquet`) | 0 | trusted |"
    )
    add(f"| {cutover} .. {trusted_end} | hourly files (`day-*.parquet`) | 1 | trusted |")
    add(
        f"| {trusted_end} + 1 .. last complete day | hourly files | 1 | degraded (flag, never train/evaluate) |"
    )
    add("")
    add(
        "`history.detail_start_date` = "
        + str(cutover)
        + ": Tier B features are NaN before it. The first trusted snapshot with a full 160-day detail look-back is therefore 2023-11-08; earlier snapshots rely on Tier A."
    )
    add("")
    add("## 4. Decision requested")
    add("")
    add(
        f"Approve running the {gb(total):,.1f} GB spine extraction this calendar month ({first_calendar_month}). Until then nothing is executed."
    )
    add("")
    return "\n".join(w)
