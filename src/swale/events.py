"""Detect rain (wetting) events from soil moisture itself.

The site rain gauge is silent from 2025-06-22 onward, so any analysis that
needs to bracket events past that date has to lean on the soil sensors as
its primary signal. Rain events show up in the shallow (10 cm) sensors as
a sharp positive ``dVWC/dt`` excursion, and in multiple sensors at once —
so a K-of-N consensus on smoothed time-derivatives is robust to single-
sensor noise.

The detector works in three steps:

1. Resample every input sensor onto a common regular grid (15 min by
   default) and bridge short gaps so the derivative is well-defined.
2. Smooth each trace with a centered moving average and take a centered
   first difference. The result is in m³/m³ per hour.
3. At each timestamp, count how many sensors exceed the threshold; runs
   where that count reaches ``min_sensors`` are events. Runs separated
   by less than ``coalesce_gap`` are merged.

The output schema mirrors ``plots/rain_events.csv`` (start/end/dur_min)
plus per-sensor consensus columns, so the downstream scripts can read
either CSV interchangeably.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from swale.preprocessing import (
    GRID_SECONDS,
    interpolate_short_gaps,
)


@dataclass(frozen=True)
class DetectorConfig:
    """Tunables for soil-based event detection.

    All physical units are explicit. Defaults reflect the 15-min logger
    cadence; ``smooth_minutes`` of 60 averages four samples, which damps
    the high-frequency sensor noise without smearing event onsets.
    """

    grid_seconds: int = GRID_SECONDS
    smooth_minutes: int = 60
    threshold_per_hour: float = 0.005          # m³/m³ per hour
    min_sensors: int = 2                        # K of N consensus
    coalesce_gap_minutes: int = 360             # merge events <6 h apart
    min_duration_minutes: int = 30              # drop sub-window blips
    max_interp_gap_minutes: int = 240           # bridge ≤4 h sensor gaps


def smoothed_derivative(
    values: np.ndarray,
    *,
    grid_seconds: int,
    smooth_minutes: int,
) -> np.ndarray:
    """Centered moving-average smooth followed by centered first difference.

    Returns dVWC/dt in (value-units) per hour. NaNs propagate through the
    smoothing window: any output sample whose smoothing window contains
    a NaN is itself NaN, which keeps the derivative honest across gaps.
    """
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)

    win = max(1, int(round(smooth_minutes * 60 / grid_seconds)))
    # Force odd window so the moving-average is centered around the sample.
    if win % 2 == 0:
        win += 1
    half = win // 2

    pad = np.concatenate([
        np.full(half, np.nan),
        values.astype(float),
        np.full(half, np.nan),
    ])
    # Cumulative-sum trick with NaN-aware mask so any NaN in window → NaN out.
    valid = (~np.isnan(pad)).astype(float)
    safe = np.where(np.isnan(pad), 0.0, pad)
    csum = np.concatenate([[0.0], np.cumsum(safe)])
    cvld = np.concatenate([[0.0], np.cumsum(valid)])
    sums = csum[win:] - csum[:-win]
    counts = cvld[win:] - cvld[:-win]
    smoothed = np.where(counts == win, sums / win, np.nan)

    # Centered first difference, in units per hour.
    dt_hours = grid_seconds / 3600.0
    dvdt = np.full(n, np.nan)
    dvdt[1:-1] = (smoothed[2:] - smoothed[:-2]) / (2 * dt_hours)
    return dvdt


def align_to_grid(
    sensor_traces: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    grid_seconds: int,
    max_interp_gap_minutes: int,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Resample every sensor onto a single common regular grid.

    Returns ``(grid_ts, {sensor_id: vals_on_grid})``. Long gaps remain NaN.
    """
    if not sensor_traces:
        return np.array([], dtype="datetime64[ns]"), {}

    starts = [ts[0] for ts, _ in sensor_traces.values() if ts.size]
    ends   = [ts[-1] for ts, _ in sensor_traces.values() if ts.size]
    if not starts:
        return np.array([], dtype="datetime64[ns]"), {}
    t0, t1 = min(starts), max(ends)

    step = np.timedelta64(grid_seconds, "s")
    grid = np.arange(t0, t1 + step, step, dtype="datetime64[ns]")

    max_gap_samples = max_interp_gap_minutes * 60 // grid_seconds
    out: dict[str, np.ndarray] = {}
    grid_us = grid.astype("datetime64[us]").astype(np.int64)
    for sid, (ts, vals) in sensor_traces.items():
        if ts.size == 0:
            out[sid] = np.full(grid.size, np.nan)
            continue
        ts_us = ts.astype("datetime64[us]").astype(np.int64)
        v = np.full(grid.size, np.nan)
        idx = np.searchsorted(grid_us, ts_us)
        # Place each observation onto the nearest grid cell. Some samples
        # may collide into the same cell (rare at 15-min cadence) — last
        # write wins, which is fine since this is just for derivative est.
        in_range = (idx < grid.size) & (idx >= 0)
        v[idx[in_range]] = vals[in_range]
        v = interpolate_short_gaps(v, max_gap=max_gap_samples)
        out[sid] = v
    return grid, out


def detect_events(
    sensor_traces: dict[str, tuple[np.ndarray, np.ndarray]],
    *,
    config: DetectorConfig | None = None,
) -> pl.DataFrame:
    """Find rain events from K-of-N consensus on shallow-sensor dVWC/dt.

    Args:
        sensor_traces: ``{sensor_id: (timestamps, values)}``. Values are
            VWC in m³/m³; timestamps are ``np.datetime64[ns]``.
        config: Detector tunables. Defaults work for the 15-min cadence.

    Returns:
        Polars frame with columns:
            event, start, end, dur_min, peak_dvwc, n_responding,
            n_sensors_total, peak_time, sensors_responding (semicolon-
            joined sensor IDs that crossed threshold during the event).
    """
    cfg = config or DetectorConfig()
    grid, aligned = align_to_grid(
        sensor_traces,
        grid_seconds=cfg.grid_seconds,
        max_interp_gap_minutes=cfg.max_interp_gap_minutes,
    )
    if grid.size == 0:
        return _empty_events_frame()

    sensor_ids = list(aligned.keys())
    n_sensors_total = len(sensor_ids)

    # Per-sensor smoothed derivatives.
    dvdt = np.stack([
        smoothed_derivative(
            aligned[sid],
            grid_seconds=cfg.grid_seconds,
            smooth_minutes=cfg.smooth_minutes,
        )
        for sid in sensor_ids
    ], axis=0)  # shape (n_sensors, n_samples)

    above = (dvdt > cfg.threshold_per_hour) & ~np.isnan(dvdt)
    consensus = above.sum(axis=0)
    in_event = consensus >= cfg.min_sensors

    runs = _runs(in_event)
    if not runs:
        return _empty_events_frame()

    # Coalesce nearby runs (gap < coalesce_gap).
    gap_samples = cfg.coalesce_gap_minutes * 60 // cfg.grid_seconds
    merged: list[tuple[int, int]] = [runs[0]]
    for s, e in runs[1:]:
        ps, pe = merged[-1]
        if s - pe <= gap_samples:
            merged[-1] = (ps, e)
        else:
            merged.append((s, e))

    # Drop sub-threshold-duration events.
    min_samples = cfg.min_duration_minutes * 60 // cfg.grid_seconds
    merged = [(s, e) for s, e in merged if (e - s) >= min_samples]
    if not merged:
        return _empty_events_frame()

    starts_a, ends_a, peaks_a = [], [], []
    durs, peak_dvdts, n_resps, sensors_resps = [], [], [], []
    for s, e in merged:
        # Per-event peak: best dVWC/dt across sensors and time within event.
        block = dvdt[:, s:e]
        if np.isnan(block).all():
            peak_dvdt = float("nan")
            peak_idx = s
        else:
            peak_idx = int(s + np.nanargmax(np.nanmax(block, axis=0)))
            peak_dvdt = float(np.nanmax(block))
        # Sensors that responded at any point during the event.
        responded = above[:, s:e].any(axis=1)
        sensors_responding = ";".join(sid for sid, r in zip(sensor_ids, responded) if r)

        start_ts = grid[s]
        end_ts   = grid[min(e, grid.size - 1)]
        peak_ts  = grid[min(peak_idx, grid.size - 1)]
        starts_a.append(start_ts)
        ends_a.append(end_ts)
        peaks_a.append(peak_ts)
        durs.append(int((end_ts - start_ts).astype("timedelta64[m]").astype(int)))
        peak_dvdts.append(peak_dvdt)
        n_resps.append(int(responded.sum()))
        sensors_resps.append(sensors_responding)

    return pl.DataFrame({
        "event":              np.arange(len(merged), dtype=np.int64),
        "start":              np.array(starts_a, dtype="datetime64[ns]"),
        "end":                np.array(ends_a, dtype="datetime64[ns]"),
        "dur_min":            np.array(durs, dtype=np.int64),
        "peak_dvwc":          np.array(peak_dvdts, dtype=np.float64),
        "n_responding":       np.array(n_resps, dtype=np.int64),
        "n_sensors_total":    np.full(len(merged), n_sensors_total, dtype=np.int64),
        "peak_time":          np.array(peaks_a, dtype="datetime64[ns]"),
        "sensors_responding": np.array(sensors_resps, dtype=object),
    })


def match_events(
    detected: pl.DataFrame,
    reference: pl.DataFrame,
    *,
    tolerance_hours: float = 6.0,
) -> dict[str, float | int]:
    """Compute precision / recall of ``detected`` events vs a reference set.

    A detected event ``D`` matches a reference event ``R`` if
    ``|D.start - R.start| ≤ tolerance_hours``. Matching is one-to-one and
    greedy in start-time order — once an ``R`` is matched it is consumed.

    Returns a small dict suitable for printing: tp, fp, fn, precision,
    recall, f1.
    """
    if detected.is_empty() or reference.is_empty():
        return {"tp": 0, "fp": detected.height, "fn": reference.height,
                "precision": 0.0, "recall": 0.0, "f1": 0.0}

    det_starts = detected["start"].to_numpy().astype("datetime64[ns]")
    ref_starts = reference["start"].to_numpy().astype("datetime64[ns]")
    tol_ns = int(tolerance_hours * 3600 * 1_000_000_000)

    used_ref = np.zeros(len(ref_starts), dtype=bool)
    tp = 0
    for ds in det_starts:
        diffs = np.abs((ref_starts - ds).astype("timedelta64[ns]").astype(np.int64))
        diffs[used_ref] = np.iinfo(np.int64).max
        j = int(np.argmin(diffs))
        if diffs[j] <= tol_ns:
            used_ref[j] = True
            tp += 1
    fp = len(det_starts) - tp
    fn = len(ref_starts) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return [lo, hi) intervals of contiguous True values in ``mask``."""
    if mask.size == 0:
        return []
    diff = np.diff(mask.astype(np.int8), prepend=0, append=0)
    starts = np.where(diff == 1)[0]
    ends   = np.where(diff == -1)[0]
    return list(zip(map(int, starts), map(int, ends)))


def _empty_events_frame() -> pl.DataFrame:
    return pl.DataFrame({
        "event":              pl.Series([], dtype=pl.Int64),
        "start":              pl.Series([], dtype=pl.Datetime("ns")),
        "end":                pl.Series([], dtype=pl.Datetime("ns")),
        "dur_min":            pl.Series([], dtype=pl.Int64),
        "peak_dvwc":          pl.Series([], dtype=pl.Float64),
        "n_responding":       pl.Series([], dtype=pl.Int64),
        "n_sensors_total":    pl.Series([], dtype=pl.Int64),
        "peak_time":          pl.Series([], dtype=pl.Datetime("ns")),
        "sensors_responding": pl.Series([], dtype=pl.Utf8),
    })
