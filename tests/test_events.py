"""Tests for the soil-based rain-event detector."""

from __future__ import annotations

import numpy as np

from swale.events import (
    DetectorConfig,
    align_to_grid,
    detect_events,
    match_events,
    smoothed_derivative,
)


GRID_S = 15 * 60  # 15-min cadence used everywhere downstream


def _grid(n: int, t0: str = "2025-01-01T00:00") -> np.ndarray:
    return (np.datetime64(t0)
            + np.arange(n) * np.timedelta64(GRID_S, "s"))


def _step_trace(n: int, jump_at: int, baseline: float = 0.20,
                 magnitude: float = 0.05, ramp: int = 4) -> np.ndarray:
    """Flat baseline, linear ramp over `ramp` samples, then flat at baseline+mag."""
    v = np.full(n, baseline)
    if jump_at + ramp < n:
        v[jump_at:jump_at + ramp] = baseline + np.linspace(
            0, magnitude, ramp, endpoint=False)
        v[jump_at + ramp:] = baseline + magnitude
    return v


def test_smoothed_derivative_recovers_step_amplitude():
    n = 200
    v = _step_trace(n, jump_at=100, magnitude=0.05, ramp=4)
    dvdt = smoothed_derivative(v, grid_seconds=GRID_S, smooth_minutes=60)
    # Peak rate should be roughly amplitude / ramp_duration in m³/m³ per hour.
    # ramp = 4 samples * 15 min = 1 h; amplitude = 0.05 → ~0.05 /hr peak.
    peak = np.nanmax(dvdt)
    assert 0.02 < peak < 0.10
    # Far from the step, derivative is ~0.
    assert abs(np.nanmean(dvdt[10:80])) < 1e-4


def test_smoothed_derivative_propagates_nan():
    v = np.full(50, 0.2)
    v[20:25] = np.nan
    dvdt = smoothed_derivative(v, grid_seconds=GRID_S, smooth_minutes=60)
    # Window of 60 min = 5 samples (forced odd) — NaN region ±2 samples.
    assert np.isnan(dvdt[20:25]).all()
    # Outside the smoothing window's reach, finite again.
    assert not np.isnan(dvdt[5])
    assert not np.isnan(dvdt[40])


def test_align_to_grid_unifies_offset_traces():
    g = _grid(100)
    # Same data, but trace B starts 30 min later and ends 30 min earlier.
    a = (g, np.linspace(0.10, 0.30, 100))
    b = (g[2:-2], np.linspace(0.10, 0.30, 96))
    grid, aligned = align_to_grid(
        {"A": a, "B": b}, grid_seconds=GRID_S, max_interp_gap_minutes=60)
    assert grid.size == 100
    # B is NaN at the edges where it had no data.
    assert np.isnan(aligned["B"][0])
    assert np.isnan(aligned["B"][-1])
    # And finite in the middle.
    assert np.isfinite(aligned["B"][50])


def test_detect_events_requires_consensus():
    n = 400
    g = _grid(n)
    # One sensor jumps at sample 200; others stay flat. min_sensors=2 → no event.
    a = _step_trace(n, jump_at=200, magnitude=0.05, ramp=4)
    b = np.full(n, 0.20)
    c = np.full(n, 0.20)
    cfg = DetectorConfig(min_sensors=2, threshold_per_hour=0.005,
                          smooth_minutes=60, coalesce_gap_minutes=60,
                          min_duration_minutes=15)
    events = detect_events({"A": (g, a), "B": (g, b), "C": (g, c)}, config=cfg)
    assert events.is_empty()


def test_detect_events_finds_consensus_jump():
    n = 400
    g = _grid(n)
    # Two sensors jump together at sample 200; one stays flat.
    a = _step_trace(n, jump_at=200, magnitude=0.05, ramp=4)
    b = _step_trace(n, jump_at=201, magnitude=0.04, ramp=4)
    c = np.full(n, 0.20)
    cfg = DetectorConfig(min_sensors=2, threshold_per_hour=0.005,
                          smooth_minutes=60, coalesce_gap_minutes=60,
                          min_duration_minutes=15)
    events = detect_events({"A": (g, a), "B": (g, b), "C": (g, c)}, config=cfg)
    assert events.height == 1
    row = events.row(0, named=True)
    assert row["n_responding"] == 2
    assert row["n_sensors_total"] == 3
    assert "A" in row["sensors_responding"]
    assert "B" in row["sensors_responding"]
    assert "C" not in row["sensors_responding"]


def test_detect_events_coalesces_close_jumps():
    n = 400
    g = _grid(n)
    # Two distinct jumps separated by ~6 h (24 samples). With a 12 h
    # coalesce window they merge into one event.
    a = np.full(n, 0.20)
    a[100:104] = np.linspace(0.20, 0.23, 4, endpoint=False)
    a[104:130] = 0.23
    a[130:134] = np.linspace(0.23, 0.26, 4, endpoint=False)
    a[134:] = 0.26
    b = a.copy()
    cfg = DetectorConfig(min_sensors=2, threshold_per_hour=0.005,
                          smooth_minutes=60, coalesce_gap_minutes=720,
                          min_duration_minutes=15)
    events = detect_events({"A": (g, a), "B": (g, b)}, config=cfg)
    assert events.height == 1


def test_detect_events_separates_distant_jumps():
    n = 600
    g = _grid(n)
    # Two jumps 3 days apart (~288 samples) — clearly separate.
    a = np.full(n, 0.20)
    a[100:104] = np.linspace(0.20, 0.25, 4, endpoint=False)
    a[104:400] = 0.25
    a[400:404] = np.linspace(0.25, 0.30, 4, endpoint=False)
    a[404:] = 0.30
    b = a.copy()
    cfg = DetectorConfig(min_sensors=2, threshold_per_hour=0.005,
                          smooth_minutes=60, coalesce_gap_minutes=60,
                          min_duration_minutes=15)
    events = detect_events({"A": (g, a), "B": (g, b)}, config=cfg)
    assert events.height == 2


def test_match_events_perfect_agreement():
    import polars as pl
    starts = np.array(["2025-01-01T10:00", "2025-01-03T15:00",
                        "2025-01-05T08:00"], dtype="datetime64[ns]")
    df = pl.DataFrame({"start": starts, "end": starts})
    score = match_events(df, df, tolerance_hours=6)
    assert score["tp"] == 3
    assert score["precision"] == 1.0
    assert score["recall"] == 1.0


def test_match_events_partial_agreement():
    import polars as pl
    det = pl.DataFrame({
        # First two match within tolerance, third is spurious.
        "start": np.array(["2025-01-01T10:30", "2025-01-03T18:00",
                            "2025-02-15T12:00"], dtype="datetime64[ns]"),
        "end":   np.array(["2025-01-01T11:00"] * 3, dtype="datetime64[ns]"),
    })
    ref = pl.DataFrame({
        # First two match a detected; third is missed.
        "start": np.array(["2025-01-01T10:00", "2025-01-03T15:00",
                            "2025-01-10T08:00"], dtype="datetime64[ns]"),
        "end":   np.array(["2025-01-01T11:00"] * 3, dtype="datetime64[ns]"),
    })
    score = match_events(det, ref, tolerance_hours=6)
    assert score["tp"] == 2
    assert score["fp"] == 1
    assert score["fn"] == 1
