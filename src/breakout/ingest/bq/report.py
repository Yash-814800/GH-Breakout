"""Render ``docs/bigquery_cost_plan.md`` from a survey and the planner output."""

from __future__ import annotations

from datetime import date

from breakout.ingest.bq import plan as P


def gb(b: float) -> float:
    return b / 1e9


def _schedule_table(quotas: list[P.QuotaMonth]) -> list[str]:
    out = ["| calendar month | GB scanned | work |", "|---|---:|---|"]
    for q in quotas:
        groups: dict[tuple[str, str], list[str]] = {}
        for u in q.units:
            groups.setdefault((u.mode, u.era), []).append(u.month)
        parts = []
        for (mode, era), ms in groups.items():
            lo, hi = min(ms), max(ms)
            span = lo if lo == hi else f"{lo}..{hi}"
            parts.append(f"{mode} {era} ({len(ms)} mo: {span})")
        out.append(f"| {q.label} | {gb(q.used):,.0f} | {'; '.join(parts)} |")
    return out


def render(
    survey: dict,
    *,
    trusted_end: date,
    cutover: date,
    budget: int,
    spent_first: int,
    first_calendar_month: str,
    hourly_estimate: dict[str, float] | None,
    generated: date,
) -> str:
    months = survey["months"]
    ms = sorted(months)
    full_months = 24
    trusted_last = f"{trusted_end:%Y-%m}"
    trusted = [m for m in ms if m <= trusted_last]
    full_set = trusted[-full_months:]
    tot = {k: sum(months[m][k] for m in ms) for k in ("spine", "full", "push")}
    full24 = sum(months[m]["full"] for m in full_set)
    spine_only = P.pack(
        P.build_units(months, trusted_end=trusted_end, order="spine_first", upgrade_rest=False)[
            : len(ms)
        ],
        budget=budget,
        first_calendar_month=first_calendar_month,
        spent_first=spent_first,
    )
    a_units = P.build_units(
        months, trusted_end=trusted_end, order="spine_first", upgrade_rest=False
    )
    b_units = P.build_units(
        months, trusted_end=trusted_end, order="detail_first", upgrade_rest=False
    )
    plan_a = P.pack(
        a_units, budget=budget, first_calendar_month=first_calendar_month, spent_first=spent_first
    )
    plan_b = P.pack(
        b_units, budget=budget, first_calendar_month=first_calendar_month, spent_first=spent_first
    )

    w: list[str] = []
    add = w.append
    add("# BigQuery cost plan (revised for the trusted era)")
    add("")
    add(
        f"Generated {generated} from `breakout backfill survey` (564 dry runs, free) over "
        f"{survey['first']}..{survey['last']}. Machine-readable: `data/manifests/bq_cost_survey.json` "
        "(git-ignored). Supersedes the Phase 2 default policy per ADR-009: full detail targets the "
        f"{full_months} months ending {trusted_last} (the trusted era), not the most recent "
        f"{full_months} months. **Nothing has been run; this needs a human decision (see the end).**"
    )
    add("")
    add("## Key numbers")
    add("")
    add(
        f"- Spine mode, **all** {len(ms)} months: **{gb(tot['spine']):,.0f} GB** (about one quota month)."
    )
    add(
        f"- Full mode (payload parsed), all months: {gb(tot['full']) / 1000:,.1f} TB; "
        f"the {full_months} trusted months alone: **{gb(full24) / 1000:,.2f} TB**. "
        f"Full mode costs ~30-40x spine in the trusted era because `payload` dominates."
    )
    add(
        f"- Monthly sandbox quota: 1 TB; project budget {gb(budget):,.0f} GB/month. "
        f"Already spent in {first_calendar_month}: {gb(spent_first):,.0f} GB (capture-quality query, "
        "`reports/capture_quality.md`)."
    )
    add(
        "- A separate `push_daily` query ("
        + f"{gb(tot['push']):,.0f} GB"
        + ") is redundant: PushEvent rows "
        "ride in the same query (their columns are already scanned) and are aggregated locally. "
        "`spine_no_push` equals `spine` byte for byte (a `type` filter never reduces bytes)."
    )
    gaps = survey.get("missing_day_tables", [])
    add(
        f"- {len(gaps)} day tables are absent from `githubarchive.day` ({', '.join(gaps)}); the months "
        "containing them are slightly under-counted below and need the month-table fallback at run time."
    )
    if hourly_estimate:
        est = sum(hourly_estimate.get(m, 0) for m in full_set)
        add(
            f"- Alternative for detail: hourly files from data.gharchive.org for the same {full_months} "
            f"months are about **{est / 1e9:,.0f} GB** of download (sampled `Content-Length`; no BigQuery "
            "quota, same parser as live ingest, so train/serve parity by construction)."
        )
    add("")
    add("## Schedules")
    add("")
    add("### A. BigQuery only, spine first (full months follow, newest first)")
    add("")
    add(f"{len(plan_a)} calendar months, finishing {plan_a[-1].label}.")
    add("")
    w.extend(_schedule_table(plan_a))
    add("")
    add("### B. BigQuery only, detail first (original Phase 2 priority)")
    add("")
    add(
        f"{len(plan_b)} calendar months; the 2015-2023 spine would not exist until {plan_b[-1].label}, "
        "so no modelling could start. Not recommended."
    )
    add("")
    w.extend(_schedule_table(plan_b))
    add("")
    add("### C. Recommended hybrid: BigQuery for spine, hourly files for detail")
    add("")
    add(
        f"1. BigQuery spine for every month: "
        f"{gb(sum(u.bytes for q in spine_only for u in q.units)):,.0f} GB over "
        f"{len(spine_only)} calendar months ({', '.join(q.label for q in spine_only)}); trusted months "
        "first, newest to oldest, degraded months last."
    )
    add(
        f"2. Detail columns for the {full_months} trusted months ({full_set[0]}..{full_set[-1]}) from "
        "hourly files on the laptop (`breakout backfill hourly-detail`, the optional Phase 2 "
        "deliverable 7), newest month first, <= 4 concurrent downloads. "
        "This costs bandwidth and local CPU only."
    )
    add(
        "3. One BigQuery full-mode day (about 15 GB) for the parity check "
        "(`breakout backfill parity`), inside the same quota month as step 1."
    )
    add(
        f"4. `detail_start_date` becomes {full_set[0]} when step 2 completes, and moves month by month "
        "as it progresses (Tier B features are NaN before it)."
    )
    add("")
    add("## Per-year totals (GB scanned)")
    add("")
    add("| year | spine | full | push (stand-alone) |")
    add("|---|---:|---:|---:|")
    for y in sorted({m[:4] for m in ms}):
        r = [m for m in ms if m.startswith(y)]
        add(
            f"| {y} | {gb(sum(months[m]['spine'] for m in r)):,.0f} | "
            f"{gb(sum(months[m]['full'] for m in r)):,.0f} | {gb(sum(months[m]['push'] for m in r)):,.0f} |"
        )
    add(
        f"| **total** | **{gb(tot['spine']):,.0f}** | **{gb(tot['full']):,.0f}** | **{gb(tot['push']):,.0f}** |"
    )
    add("")
    add("## Per-month bytes (GB scanned)")
    add("")
    add("| month | era | spine | full | push | full/spine |")
    add("|---|---|---:|---:|---:|---:|")
    for m in ms:
        era = "trusted" if m <= trusted_last else "degraded"
        v = months[m]
        add(
            f"| {m} | {era} | {gb(v['spine']):,.1f} | {gb(v['full']):,.1f} | {gb(v['push']):,.1f} "
            f"| {v['full'] / v['spine']:.0f} |"
        )
    add("")
    add("## Decisions needed (HUMAN DECISION in Phase 2)")
    add("")
    add(
        f"1. `history.cutover_date`: proposed **{cutover}** (first day of the OpenDigger-era hourly feed). "
        "The BigQuery backfill then covers `[2015-01-01, cutover)`; the Phase 2 default (first day of "
        "the current month) would leave 2026-09-06..2026-09-30 to be re-ingested twice."
    )
    add("2. Approve schedule C (recommended), A, or B.")
    add(
        "3. Degraded months (2025-06..2026-09-05) are spine-only in every schedule; they are kept for "
        "context and for live-scoring look-back windows, never for training/evaluation."
    )
    add("")
    return "\n".join(w)
