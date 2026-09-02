"""Pure numerical statistics for metric anomaly detection."""

from __future__ import annotations

import statistics
from collections.abc import Sequence


def moving_average(values: Sequence[float]) -> float:
    """Return the arithmetic mean of ``values``."""

    if not values:
        msg = "values must not be empty"
        raise ValueError(msg)
    return statistics.fmean(values)


def standard_deviation(values: Sequence[float]) -> float:
    """Return the sample standard deviation of ``values``."""

    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def z_score(value: float, mean: float, stddev: float, *, min_stddev: float) -> float:
    """Compute the z-score of ``value`` relative to a baseline distribution."""

    denominator = max(stddev, min_stddev)
    return (value - mean) / denominator


def percentage_change(current: float, previous: float) -> float | None:
    """Return percentage change from ``previous`` to ``current``."""

    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100.0


def percentile_rank(value: float, values: Sequence[float]) -> float:
    """Return the percentile rank of ``value`` within ``values`` (0-100)."""

    if not values:
        msg = "values must not be empty"
        raise ValueError(msg)
    sorted_values = sorted(values)
    count_below = sum(1 for item in sorted_values if item < value)
    count_equal = sum(1 for item in sorted_values if item == value)
    # Mid-rank method for ties.
    rank = count_below + (count_equal - 1) / 2
    return (rank / (len(sorted_values) - 1)) * 100.0 if len(sorted_values) > 1 else 50.0


def rolling_statistics(
    history: Sequence[float],
    *,
    current: float,
    window_size: int,
    min_stddev: float,
    previous: float | None = None,
) -> tuple[float, float, float, float | None, float | None, float | None]:
    """Compute rolling mean, stddev, z-score, percentile, and pct change."""

    window = list(history[-window_size:])
    mean = moving_average(window)
    stddev = standard_deviation(window)
    z = z_score(current, mean, stddev, min_stddev=min_stddev)
    pct_rank = percentile_rank(current, window + [current])
    pct_change = (
        percentage_change(current, previous)
        if previous is not None
        else percentage_change(current, mean)
    )
    return mean, stddev, z, pct_rank, pct_change, mean
