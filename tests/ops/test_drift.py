from __future__ import annotations

import numpy as np
import pandas as pd

from breakout.ops import drift


def test_calculate_psi_identical_distribution() -> None:
    rng = np.random.default_rng(42)
    expected = rng.normal(loc=10.0, scale=2.0, size=2000)
    actual = rng.normal(loc=10.0, scale=2.0, size=2000)

    psi = drift.calculate_psi(expected, actual, num_bins=10)
    assert psi < 0.1, f"Expected low PSI for identical distributions, got {psi}"


def test_calculate_psi_shifted_distribution() -> None:
    rng = np.random.default_rng(42)
    expected = rng.normal(loc=10.0, scale=2.0, size=2000)
    # Significant distribution shift
    actual = rng.normal(loc=20.0, scale=2.0, size=2000)

    psi = drift.calculate_psi(expected, actual, num_bins=10)
    assert psi > drift.DRIFT_THRESHOLD, f"Expected PSI > {drift.DRIFT_THRESHOLD}, got {psi}"


def test_calculate_psi_empty_or_nans() -> None:
    assert drift.calculate_psi(np.array([]), np.array([])) == 0.0
    assert drift.calculate_psi(np.array([np.nan, np.nan]), np.array([1.0, 2.0])) == 0.0


def test_calculate_categorical_psi() -> None:
    expected = pd.Series(["Python"] * 80 + ["TypeScript"] * 20)
    actual_same = pd.Series(["Python"] * 82 + ["TypeScript"] * 18)
    actual_shifted = pd.Series(["Python"] * 10 + ["TypeScript"] * 90)

    psi_same = drift.calculate_categorical_psi(expected, actual_same)
    assert psi_same < 0.1, f"Expected low categorical PSI, got {psi_same}"

    psi_shifted = drift.calculate_categorical_psi(expected, actual_shifted)
    assert psi_shifted > drift.DRIFT_THRESHOLD, f"Expected high categorical PSI, got {psi_shifted}"
