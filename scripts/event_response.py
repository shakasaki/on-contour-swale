"""Soil-moisture time-trace around a single rain event.

Cuts a window starting ``DAYS_BEFORE`` days before ``EVENT_DATE`` and
extending ``DAYS_AFTER`` days after, then plots all sensors at each depth
on shared axes so we can compare treatment responses to the same event.

Default event: 2025-06-11, the 39.2 mm hit that follows three quiet days
and is followed by ~11 dry days — a clean drydown window.

Layout:
    Row 0:  precipitation (native 15-min cadence, log y)
    Row 1:  all 10 cm sensors  (4 swale + 3 control)
    Row 2:  all 40 cm sensors  (4 swale + 3 control + SMS10 'step')

Within each soil row: color = treatment, line style cycles through sensors
of that treatment so each sensor is identifiable even when curves overlap.
Legend uses the metadata 'tag' (slope/mount/down/far/top/middle/bottom).

Run from project root::

    .venv/bin/python scripts/event_response.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from matplotlib.gridspec import GridSpec

from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables — change these to play with the analysis.
# ---------------------------------------------------------------------------

EVENT_DATE = datetime(2025, 6, 11)   # peak day of the rain event
DAYS_BEFORE = 3                       # context window before the event
DAYS_AFTER = 25                       # drydown window after

DEPTHS_TO_PLOT: list[int] = [10, 40]

# Treatment palette + per-sensor linestyle cycles. Cycling linestyles
# within a treatment keeps overlapping curves distinguishable while the
# treatment color stays consistent for at-a-glance grouping.
TREATMENT_COLOR = {"swale": "#1f77b4", "control": "#d62728"}
LINESTYLES = ["-", "--", "-.", ":"]

# Logger that carries the rain gauge.
RAIN_LOGGER = "19570"

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("/home/alexis/DATA/swale")
METADATA = DATA_ROOT / "Metadata.xlsx"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"


# ---------------------------------------------------------------------------
# Data slicing
# ---------------------------------------------------------------------------

def cut_window(df: pl.DataFrame, t0: datetime,
                t1: datetime) -> pl.DataFrame:
    """Restrict the long-format frame to [t0, t1]."""
    return df.filter((pl.col("timestamp") >= t0)
                      & (pl.col("timestamp") <= t1))


def sensors_at_depth(df: pl.DataFrame, depth: int):
    """Return [(sensor_id, treatment, location, tag), ...] for moisture
    sensors at this depth, swale first then control, then by sensor_id.
    """
    rows = (df.filter((pl.col("variable") == "moisture")
                       & (pl.col("depth_cm") == depth)
                       & pl.col("treatment").is_not_null())
              .select(["sensor_id", "treatment", "location", "tag"])
              .unique()
              .sort(["treatment", "sensor_id"])
              .to_dicts())
    out = []
    for treatment in ("swale", "control"):
        for r in rows:
            if r["treatment"] == treatment:
                out.append((r["sensor_id"], r["treatment"],
                            r["location"], r["tag"]))
    return out


def sensor_trace(df: pl.DataFrame, sensor_id: str
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Return (timestamps, values) for one moisture sensor in the window.

    No resampling, no gap-bridging — we want the raw trace for an event
    plot. Any single dropout shows up as a missing point in the line.
    """
    g = (df.filter((pl.col("variable") == "moisture")
                    & (pl.col("sensor_id") == sensor_id)
                    & pl.col("value").is_not_null())
            .select(["timestamp", "value"])
            .sort("timestamp"))
    return g["timestamp"].to_numpy(), g["value"].to_numpy()


def cumulative_rain(df: pl.DataFrame
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Return (timestamps, cumulative_mm) over the windowed frame.

    Includes zero-valued samples so the line stays flat between events.
    Cumulative is a cleaner line-form than the bar/vlines view: flat where
    no rain, steep where heavy, total height = total mm in the window.
    """
    rain = (df.filter((pl.col("logger_serial") == RAIN_LOGGER)
                       & (pl.col("variable") == "precipitation")
                       & pl.col("value").is_not_null())
              .sort("timestamp"))
    if rain.is_empty():
        return np.array([], dtype="datetime64[ns]"), np.array([])
    ts = rain["timestamp"].to_numpy()
    cum = np.cumsum(rain["value"].to_numpy())
    return ts, cum


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_event(df_full: pl.DataFrame, out: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper")

    t0 = EVENT_DATE - timedelta(days=DAYS_BEFORE)
    t1 = EVENT_DATE + timedelta(days=DAYS_AFTER)
    df = cut_window(df_full, t0, t1)

    rain_ts, rain_cum = cumulative_rain(df)
    daily_total = float(rain_cum[-1]) if rain_cum.size else 0.0

    n_rows = 1 + len(DEPTHS_TO_PLOT)
    fig = plt.figure(figsize=(14, 2.0 + 2.6 * len(DEPTHS_TO_PLOT)))
    gs = GridSpec(n_rows, 1, height_ratios=[0.6] + [1.0] * len(DEPTHS_TO_PLOT),
                   figure=fig, hspace=0.18)
    fig.suptitle(
        f"Soil moisture response — rain event "
        f"{EVENT_DATE.strftime('%Y-%m-%d')} "
        f"(window: {DAYS_BEFORE} d before → {DAYS_AFTER} d after, "
        f"{daily_total:.1f} mm in window)",
        fontsize=13, weight="bold")

    # --- Rain row -------------------------------------------------------
    ax_rain = fig.add_subplot(gs[0])
    if rain_ts.size:
        ax_rain.plot(rain_ts, rain_cum,
                      color="#1f77b4", linewidth=1.6)
        ax_rain.set_ylim(0, max(rain_cum) * 1.05)
    ax_rain.set_ylabel("Cumulative rain\n(mm)", fontsize=9)
    ax_rain.set_xlim(t0, t1)
    ax_rain.tick_params(labelbottom=False)
    ax_rain.grid(alpha=0.3)
    # Mark the event peak day for visual reference on every subplot.
    ax_rain.axvline(EVENT_DATE, color="k", linestyle=":",
                     linewidth=0.8, alpha=0.5)

    # --- One row per depth ---------------------------------------------
    for row_i, depth in enumerate(DEPTHS_TO_PLOT, start=1):
        ax = fig.add_subplot(gs[row_i], sharex=ax_rain)
        sensors = sensors_at_depth(df, depth)

        # Cycle linestyles per treatment so curves of the same color stay
        # distinguishable. We rebuild the cycle index per treatment.
        ls_idx = {"swale": 0, "control": 0}
        for sid, treatment, location, tag in sensors:
            ts, vals = sensor_trace(df, sid)
            if ts.size == 0:
                continue
            ls = LINESTYLES[ls_idx[treatment] % len(LINESTYLES)]
            ls_idx[treatment] += 1
            ax.plot(ts, vals,
                     color=TREATMENT_COLOR[treatment],
                     linestyle=ls,
                     linewidth=1.3,
                     alpha=0.85,
                     label=f"{treatment[:2]}-{tag} ({sid})")

        ax.axvline(EVENT_DATE, color="k", linestyle=":",
                    linewidth=0.8, alpha=0.5)
        ax.set_ylabel(f"VWC at {depth} cm\n(m³/m³)", fontsize=10)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", ncol=2, fontsize=8, framealpha=0.9)
        if row_i < n_rows - 1:
            ax.tick_params(labelbottom=False)

    # X-axis: daily ticks on the bottom row
    bottom = fig.axes[-1]
    bottom.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    bottom.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    fig.subplots_adjust(top=0.93, bottom=0.10, left=0.07, right=0.98)
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print("Loading dataset (cached if available)…")
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )
    print(f"  {df.height:,} rows")

    out = PLOTS / f"event_{EVENT_DATE.strftime('%Y%m%d')}.png"
    print(f"Plotting event window → {out}")
    plot_event(df, out)
    print("Done.")


if __name__ == "__main__":
    main()
