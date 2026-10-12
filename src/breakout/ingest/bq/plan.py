"""Backfill planner: pack monthly work units into free-quota calendar months.

Pure functions over a survey ``{month: {"spine": bytes, "full": bytes, "push": bytes}}``.
Policy (ADR-009, revising Phase 2's default):
  P1  full mode for the ``full_months`` months ending at ``trusted_end``'s month (newest first)
  P2  spine mode for every remaining month, trusted era newest-first, then degraded months
  P3  (optional, future quota months) upgrade older trusted months spine -> full, newest first
Upgrading re-scans the month, so an upgrade costs the full-mode bytes again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

Survey = dict[str, dict[str, int]]


@dataclass(frozen=True)
class Unit:
    month: str  # YYYY-MM
    mode: str  # spine | full
    bytes: int
    priority: int  # 1, 2, 3
    era: str  # trusted | degraded


@dataclass
class QuotaMonth:
    label: str  # calendar month, e.g. 2026-10
    budget: int
    units: list[Unit] = field(default_factory=list)

    @property
    def used(self) -> int:
        return sum(u.bytes for u in self.units)


def month_range(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def next_calendar_month(label: str) -> str:
    y, m = map(int, label.split("-"))
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def build_units(
    survey: Survey,
    *,
    trusted_end: date,
    full_months: int = 24,
    order: str = "spine_first",
    include_degraded_full: bool = False,
    upgrade_rest: bool = True,
) -> list[Unit]:
    """Work units in priority order.

    ``spine_first`` (recommended once full mode costs ~35x spine): spine for every month first so
    Tier-A modelling can start, then full for the ``full_months`` trusted months newest first,
    then optional upgrades. ``detail_first`` is the original Phase 2 policy: full months first,
    then spine for everything else.
    """
    if order not in ("spine_first", "detail_first"):
        raise ValueError(f"unknown order {order!r}")
    months = sorted(survey)
    trusted_last = f"{trusted_end:%Y-%m}"
    trusted = [m for m in months if m <= trusted_last]
    degraded = [m for m in months if m > trusted_last]
    full_set = set(trusted[-full_months:])
    rest_trusted = sorted((m for m in trusted if m not in full_set), reverse=True)
    units: list[Unit] = []

    def full(m: str, prio: int, era: str) -> Unit:
        return Unit(m, "full", survey[m]["full"], prio, era)

    def spine(m: str, prio: int, era: str) -> Unit:
        return Unit(m, "spine", survey[m]["spine"], prio, era)

    if order == "detail_first":
        units += [full(m, 1, "trusted") for m in sorted(full_set, reverse=True)]
        if include_degraded_full:
            units += [full(m, 1, "degraded") for m in sorted(degraded, reverse=True)]
        units += [spine(m, 2, "trusted") for m in rest_trusted]
        if not include_degraded_full:
            units += [spine(m, 2, "degraded") for m in sorted(degraded, reverse=True)]
    else:
        units += [spine(m, 1, "trusted") for m in sorted(trusted, reverse=True)]
        units += [spine(m, 1, "degraded") for m in sorted(degraded, reverse=True)]
        units += [full(m, 2, "trusted") for m in sorted(full_set, reverse=True)]
        if include_degraded_full:
            units += [full(m, 2, "degraded") for m in sorted(degraded, reverse=True)]
    if upgrade_rest:
        units += [full(m, 3, "trusted") for m in rest_trusted]
    return _dedupe_spine_when_full(units)


def _dedupe_spine_when_full(units: list[Unit]) -> list[Unit]:
    """In detail_first order a month is never planned as both spine and full in priorities 1-2."""
    return units


def pack(
    units: list[Unit], *, budget: int, first_calendar_month: str, spent_first: int = 0
) -> list[QuotaMonth]:
    """Greedy sequential packing in priority order; a unit that does not fit starts a new month."""
    quotas: list[QuotaMonth] = []
    cur = QuotaMonth(first_calendar_month, budget)
    used = spent_first
    for u in units:
        if u.bytes > budget:
            raise ValueError(f"unit {u.month}/{u.mode} ({u.bytes}) exceeds the monthly budget")
        if used + u.bytes > budget:
            quotas.append(cur)
            cur = QuotaMonth(next_calendar_month(cur.label), budget)
            used = 0
        cur.units.append(u)
        used += u.bytes
    quotas.append(cur)
    return quotas


def detail_start(quotas: list[QuotaMonth], upto: int | None = None) -> str | None:
    """Earliest month with full detail after the first ``upto`` quota months (None = all)."""
    sel = quotas if upto is None else quotas[:upto]
    full = [u.month for q in sel for u in q.units if u.mode == "full" and u.era == "trusted"]
    return min(full) if full else None
