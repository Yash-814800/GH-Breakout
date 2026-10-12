from __future__ import annotations

from datetime import date

import pytest

from breakout.ingest.bq import plan as P
from breakout.ingest.bq import sql as Q
from breakout.schema import EVENTS_COLUMNS

GB = 1_000_000_000


def _select_aliases(sql: str) -> list[str]:
    """Output column names of the top-level SELECT list (one expression may span many lines)."""
    import re

    head = sql.split("\nFROM ")[0].removeprefix("SELECT\n")
    items, depth, cur = [], 0, ""
    for ch in head:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    out = []
    for item in items:
        m = re.search(r"\bAS (\w+)\s*$", item.strip())
        out.append(m.group(1) if m else item.strip())
    return out


def test_spine_sql_never_references_payload() -> None:
    sql = Q.raw_events_sql(date(2024, 6, 1), date(2024, 6, 7), "spine")
    assert "payload" not in sql.lower()
    assert "SELECT *" not in sql.upper()


def test_full_sql_references_payload_once_per_field_and_has_all_columns() -> None:
    sql = Q.raw_events_sql(date(2024, 6, 1), date(2024, 6, 7), "full")
    assert "payload" in sql
    expected = [
        c
        for c in EVENTS_COLUMNS
        if c not in ("event_type", "detail_level", "source", "ingested_at")
    ]
    expected.insert(1, "event_type")
    aliases = _select_aliases(sql)
    assert aliases == expected  # same names and order as the slim schema (minus writer columns)


def test_spine_and_full_have_same_output_columns() -> None:
    a = _select_aliases(Q.raw_events_sql(date(2024, 6, 1), date(2024, 6, 1), "spine"))
    b = _select_aliases(Q.raw_events_sql(date(2024, 6, 1), date(2024, 6, 1), "full"))
    assert a == b


def test_table_suffix_is_six_digits_and_in_where() -> None:
    sql = Q.raw_events_sql(date(2015, 1, 1), date(2015, 1, 7), "spine")
    assert "_TABLE_SUFFIX BETWEEN '150101' AND '150107'" in sql
    assert "githubarchive.day.20*" in sql
    assert "PushEvent" in sql and "@raw_types" in sql
    assert "PushEvent" not in Q.raw_events_sql(
        date(2015, 1, 1), date(2015, 1, 7), "spine", include_push=False
    )


def test_bad_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        Q.raw_events_sql(date(2024, 6, 7), date(2024, 6, 1), "spine")
    with pytest.raises(ValueError):
        Q.raw_events_sql(date(2024, 6, 1), date(2024, 6, 7), "everything")
    with pytest.raises(ValueError):
        Q.validate_types(["WatchEvent'; DROP"])


def _survey() -> P.Survey:
    out = {}
    for m in P.month_range("2023-01", "2025-08"):
        out[m] = {"spine": 10 * GB, "full": 400 * GB, "push": 5 * GB}
    return out


def test_month_helpers() -> None:
    assert P.month_range("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    assert P.next_calendar_month("2026-12") == "2027-01"


def test_spine_first_orders_spine_before_full_and_marks_eras() -> None:
    units = P.build_units(
        _survey(), trusted_end=date(2025, 5, 31), full_months=24, upgrade_rest=False
    )
    first_full = next(i for i, u in enumerate(units) if u.mode == "full")
    assert all(u.mode == "spine" for u in units[:first_full])
    spine_months = {u.month for u in units if u.mode == "spine"}
    assert spine_months == set(_survey())  # every month has spine
    full = [u for u in units if u.mode == "full"]
    assert len(full) == 24
    assert full[0].month == "2025-05" and full[-1].month == "2023-06"  # newest first
    assert {u.era for u in units if u.month > "2025-05"} == {"degraded"}
    assert all(u.mode == "spine" for u in units if u.era == "degraded")


def test_detail_first_puts_full_first() -> None:
    units = P.build_units(
        _survey(), trusted_end=date(2025, 5, 31), order="detail_first", upgrade_rest=False
    )
    assert units[0].mode == "full" and units[0].month == "2025-05"
    assert units[23].mode == "full" and units[24].mode == "spine"


def test_pack_respects_budget_and_spent() -> None:
    units = [P.Unit(f"2025-0{i}", "full", 400 * GB, 1, "trusted") for i in range(1, 6)]
    q = P.pack(units, budget=900 * GB, first_calendar_month="2026-10")
    assert [len(x.units) for x in q] == [2, 2, 1]
    assert [x.label for x in q] == ["2026-10", "2026-11", "2026-12"]
    q2 = P.pack(units, budget=900 * GB, first_calendar_month="2026-10", spent_first=200 * GB)
    assert [len(x.units) for x in q2] == [1, 2, 2]
    with pytest.raises(ValueError):
        P.pack(
            [P.Unit("2025-01", "full", 901 * GB, 1, "trusted")],
            budget=900 * GB,
            first_calendar_month="2026-10",
        )


def test_detail_start() -> None:
    units = P.build_units(_survey(), trusted_end=date(2025, 5, 31), upgrade_rest=False)
    q = P.pack(units, budget=900 * GB, first_calendar_month="2026-10")
    assert P.detail_start(q) == "2023-06"
    assert P.detail_start(q, upto=1) is None or P.detail_start(q, upto=1) >= "2023-06"
