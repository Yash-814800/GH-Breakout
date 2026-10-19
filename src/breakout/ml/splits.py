"""Rolling-origin folds with an embargo (CLAUDE.md section 6).

Callers pass MATURED snapshot dates only (``mart_snapshot_dates.is_label_matured``); nothing
here can tell a matured date from an unmatured one.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal


@dataclass(frozen=True)
class Fold:
    train_dates: tuple[date, ...]
    test_dates: tuple[date, ...]
    test_start: date
    test_end: date  # exclusive end of the test block


def add_months(d: date, months: int) -> date:
    """First-of-month arithmetic helper: ``d`` moved by ``months``, day clipped to the month end."""
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def make_folds(
    snapshot_dates: Iterable[date],
    *,
    test_window_months: int,
    embargo_days: int,
    min_train_years: int,
    horizon_days: int,
    mode: Literal["expanding", "sliding"] = "expanding",
    sliding_years: int | None = None,
) -> list[Fold]:
    """Consecutive, non-overlapping calendar blocks of ``test_window_months`` as test sets.

    The first block starts on the first day of the month on or after ``min_train_years`` years from
    the first snapshot. ``train_dates = {d : d <= test_start - embargo_days}`` (expanding) or that
    set restricted to the last ``sliding_years`` years before the cut-off (sliding). The last block
    may be shorter than the others; blocks without snapshots are skipped.
    """
    if embargo_days < horizon_days:
        raise ValueError(f"embargo_days ({embargo_days}) must be >= horizon_days ({horizon_days})")
    if mode == "sliding" and not sliding_years:
        raise ValueError("sliding mode needs sliding_years")
    dates = sorted(set(snapshot_dates))
    if not dates:
        return []
    first, last = dates[0], dates[-1]
    # first of the month on or after first + min_train_years
    target = add_months(first, 12 * min_train_years)
    start = date(target.year, target.month, 1)
    if start < target:
        start = add_months(start, 1)

    folds: list[Fold] = []
    while start <= last:
        end = add_months(start, test_window_months)
        test = tuple(d for d in dates if start <= d < end)
        cutoff = start - timedelta(days=embargo_days)
        lower = None
        if mode == "sliding":
            assert sliding_years is not None
            lower = add_months(cutoff, -12 * sliding_years)
        train = tuple(d for d in dates if d <= cutoff and (lower is None or d > lower))
        if test and train:
            folds.append(Fold(train, test, start, end))
        start = end
    return folds
