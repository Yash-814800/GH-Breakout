from datetime import date, timedelta

import pytest

from breakout.ml.splits import add_months, make_folds


def mondays(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


DATES = mondays(date(2016, 1, 4), date(2020, 12, 28))
KW = dict(test_window_months=3, embargo_days=30, min_train_years=2, horizon_days=30)


def test_add_months_clips_day():
    assert add_months(date(2020, 1, 31), 1) == date(2020, 2, 29)
    assert add_months(date(2020, 11, 15), 3) == date(2021, 2, 15)
    assert add_months(date(2020, 3, 10), -12) == date(2019, 3, 10)


def test_first_block_after_min_train_years():
    folds = make_folds(DATES, **KW)
    assert folds[0].test_start == date(
        2018, 2, 1
    )  # 2016-01-04 + 2y = 2018-01-04 -> next month start
    assert min(folds[0].train_dates) == DATES[0]


def test_no_train_date_within_embargo():
    for f in make_folds(DATES, **KW):
        assert max(f.train_dates) <= f.test_start - timedelta(days=30)
        assert max(f.train_dates) < min(f.test_dates)


def test_test_blocks_consecutive_and_disjoint():
    folds = make_folds(DATES, **KW)
    for a, b in zip(folds, folds[1:], strict=False):
        assert a.test_end == b.test_start
        assert not set(a.test_dates) & set(b.test_dates)
    for f in folds:
        assert all(f.test_start <= d < f.test_end for d in f.test_dates)


def test_only_given_dates_are_used():
    matured = [d for d in DATES if d <= date(2020, 6, 1)]
    folds = make_folds(matured, **KW)
    used = {d for f in folds for d in (*f.train_dates, *f.test_dates)}
    assert used <= set(matured)
    assert folds[-1].test_dates[-1] == matured[-1]


def test_sliding_window_length():
    folds = make_folds(DATES, mode="sliding", sliding_years=1, **KW)
    for f in folds:
        cutoff = f.test_start - timedelta(days=30)
        assert min(f.train_dates) > add_months(cutoff, -12)
        assert 50 <= len(f.train_dates) <= 53


def test_embargo_must_cover_horizon():
    with pytest.raises(ValueError):
        make_folds(DATES, **{**KW, "embargo_days": 29})


def test_sliding_needs_years():
    with pytest.raises(ValueError):
        make_folds(DATES, mode="sliding", **KW)


def test_empty_and_too_short():
    assert make_folds([], **KW) == []
    assert make_folds(DATES[:50], **KW) == []
