"""Time-series preprocessing helpers for spectral analysis.

Resamples a per-sensor (timestamp, value) frame onto a regular grid,
linearly interpolates short gaps, and returns the longest contiguous
finite segment. FFT-family methods all need uniform sampling and no NaNs;
these helpers provide that.
"""

from __future__ import annotations

import numpy as np
import polars as pl

# Native logger cadence
GRID = "15m"
GRID_SECONDS = 15 * 60
SAMPLES_PER_DAY = 24 * 60 // 15

# Defaults — callers can override.
DEFAULT_MAX_INTERP_GAP_S = 4 * 3600        # interpolate gaps ≤ 4 h
DEFAULT_MIN_SEGMENT_DAYS = 30              # require ≥30 d of contiguous data


def regular_series(
    group: pl.DataFrame,
    *,
    max_interp_gap_s: int = DEFAULT_MAX_INTERP_GAP_S,
    min_segment_days: int = DEFAULT_MIN_SEGMENT_DAYS,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Resample one sensor's series to 15-min and return its longest gap-free run.

    Steps:
      1. Sort by timestamp, drop nulls.
      2. Upsample to a uniform 15-min grid (gaps become NaN).
      3. Linear-interpolate runs of NaN whose length ≤ max_interp_gap_s.
      4. Find the longest contiguous finite run.
      5. Return (timestamps, values) for that run, or None if no run is long
         enough (must be ≥ min_segment_days × 96 samples).

    Args:
        group: A polars frame with at least 'timestamp' and 'value' columns.
        max_interp_gap_s: Max gap length to bridge by linear interpolation.
        min_segment_days: Minimum contiguous-segment length to be usable.

    Returns:
        (ts: ndarray[datetime64], vals: ndarray[float64]) or None.
    """
    g = (group.select(["timestamp", "value"])
              .filter(pl.col("value").is_not_null())
              .sort("timestamp"))
    if g.height < 2:
        return None

    up = (g.upsample(time_column="timestamp", every=GRID, maintain_order=True)
            .sort("timestamp"))
    ts = up["timestamp"].to_numpy()
    val = up["value"].to_numpy().astype(float)

    val = interpolate_short_gaps(val,
                                 max_gap=max_interp_gap_s // GRID_SECONDS)
    seg = longest_contiguous(val)
    if seg is None:
        return None
    lo, hi = seg
    n_min = min_segment_days * SAMPLES_PER_DAY
    if (hi - lo) < n_min:
        return None
    return ts[lo:hi], val[lo:hi]


def interpolate_short_gaps(x: np.ndarray, *, max_gap: int) -> np.ndarray:
    """Linear-interpolate runs of NaN whose length ≤ max_gap samples.

    Longer gaps stay NaN so the contiguous-segment search breaks on them.
    Edge NaNs (at the very start or end of the array) are not extrapolated.
    """
    x = x.copy()
    isnan = np.isnan(x)
    if not isnan.any():
        return x
    diff = np.diff(isnan.astype(np.int8), prepend=0, append=0)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    for s, e in zip(starts, ends):
        gap_len = e - s
        if gap_len > max_gap or s == 0 or e == len(x):
            continue
        left = x[s - 1]
        right = x[e]
        x[s:e] = np.linspace(left, right, gap_len + 2)[1:-1]
    return x


def longest_contiguous(x: np.ndarray) -> tuple[int, int] | None:
    """Return [lo, hi) of the longest run of finite values, or None."""
    valid = ~np.isnan(x)
    if not valid.any():
        return None
    diff = np.diff(valid.astype(np.int8), prepend=0, append=0)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    if len(starts) == 0:
        return None
    lengths = ends - starts
    i = int(np.argmax(lengths))
    return int(starts[i]), int(ends[i])
