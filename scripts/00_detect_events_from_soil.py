"""Detect rain (wetting) events from the 10 cm soil-moisture sensors.

The site rain gauge is silent from 2025-06-22 22:15 onward (mechanical
fault). Past that date, the only reliable signal we have for wetting is
the soil moisture itself: a rain event shows up as a sharp positive
``dVWC/dt`` excursion across multiple shallow sensors at once.

This script:

  1. Loads the dataset and pulls every 10 cm moisture trace (swale +
     control combined; we want all of them voting on whether a wetting
     happened).
  2. Runs ``swale.events.detect_events`` with a K-of-N consensus rule
     on smoothed time-derivatives.
  3. *Validates* the detector against the gauge-derived
     ``plots/rain_events.csv`` over the period the gauge actually
     worked (start of record → 2025-06-22). Reports precision / recall.
  4. Writes ``plots/events_from_soil.csv`` covering the *full* record,
     and renders a comparison plot at
     ``plots/events_from_soil_validation.png``.

Tunables are exposed at the top of the script.

Run from project root::

    .venv/bin/python scripts/00_detect_events_from_soil.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from swale.events import (
    DetectorConfig,
    detect_events,
    match_events,
)
from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Detector configuration. These were picked by sanity-checking against
# the 84-event gauge-derived list — a 0.005 m³/m³ per hour threshold with
# 2-of-N consensus catches the bulk of gauge events while staying quiet
# during dry spells.
DETECTOR = DetectorConfig(
    smooth_minutes=60,
    threshold_per_hour=0.005,
    min_sensors=2,
    coalesce_gap_minutes=360,
    min_duration_minutes=30,
    max_interp_gap_minutes=240,
)

# Validation window — the gauge worked from start of record to here.
GAUGE_VALID_END = datetime(2025, 6, 22, 22, 15)

# Match tolerance when comparing detected events to gauge events.
MATCH_TOLERANCE_HOURS = 6.0

# Detection depth (cm). Shallow sensors respond promptly to wetting;
# 40 cm is too damped/lagged in the swale to be a reliable trigger.
DETECTION_DEPTH_CM = 10

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("/home/alexis/DATA/swale")
METADATA = DATA_ROOT / "Metadata.xlsx"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

GAUGE_EVENTS_CSV = PLOTS / "rain_events.csv"
SOIL_EVENTS_CSV  = PLOTS / "00_events_from_soil.csv"
VALIDATION_PNG   = PLOTS / "00_events_from_soil_validation.png"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_shallow_traces(df: pl.DataFrame, depth_cm: int
                            ) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return ``{sensor_id: (timestamps, values)}`` for moisture sensors at depth."""
    sub = (df.filter((pl.col("variable") == "moisture")
                      & (pl.col("depth_cm") == depth_cm)
                      & pl.col("treatment").is_not_null()
                      & pl.col("value").is_not_null())
             .select(["sensor_id", "timestamp", "value"])
             .sort(["sensor_id", "timestamp"]))
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for sid, group in sub.group_by("sensor_id"):
        ts = group["timestamp"].to_numpy().astype("datetime64[ns]")
        v = group["value"].to_numpy().astype(float)
        out[str(sid[0]) if isinstance(sid, tuple) else str(sid)] = (ts, v)
    return out


def load_gauge_events() -> pl.DataFrame:
    """Read the existing gauge-derived events CSV."""
    if not GAUGE_EVENTS_CSV.exists():
        raise FileNotFoundError(GAUGE_EVENTS_CSV)
    return pl.read_csv(
        GAUGE_EVENTS_CSV,
        try_parse_dates=True,
        schema_overrides={"start": pl.Datetime("ns"),
                           "end":   pl.Datetime("ns")},
    )


def cumulative_rain(df: pl.DataFrame
                     ) -> tuple[np.ndarray, np.ndarray]:
    """All-record cumulative rain — bounds the gauge-valid period visually."""
    rain = (df.filter((pl.col("variable") == "precipitation")
                       & (pl.col("logger_serial") == "19570")
                       & pl.col("value").is_not_null())
              .sort("timestamp"))
    if rain.is_empty():
        return np.array([], dtype="datetime64[ns]"), np.array([])
    ts = rain["timestamp"].to_numpy().astype("datetime64[ns]")
    cum = np.cumsum(rain["value"].to_numpy())
    return ts, cum


# ---------------------------------------------------------------------------
# Validation + plot
# ---------------------------------------------------------------------------

def make_validation_plot(
    df: pl.DataFrame,
    soil_events: pl.DataFrame,
    gauge_events: pl.DataFrame,
    out: Path,
) -> None:
    """Three-row plot: rain trace, 10 cm VWC + event spans, event-onset rug."""
    sns.set_theme(style="whitegrid", context="paper")

    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True,
                              gridspec_kw={"height_ratios": [1.0, 1.6, 0.4]})
    ax_rain, ax_sm, ax_rug = axes

    # --- Rain row -------------------------------------------------------
    rt, rc = cumulative_rain(df)
    if rt.size:
        ax_rain.plot(rt, rc, color="#1f77b4", lw=1.2, label="Cumulative rain")
        ax_rain.axvline(GAUGE_VALID_END, color="k", ls=":", lw=0.8,
                          alpha=0.6, label="Gauge silent →")
    ax_rain.set_ylabel("Rain (mm, cum.)", fontsize=9)
    ax_rain.legend(loc="upper left", fontsize=8)

    # --- Soil moisture row with detected events shaded ------------------
    sm = (df.filter((pl.col("variable") == "moisture")
                     & (pl.col("depth_cm") == DETECTION_DEPTH_CM)
                     & pl.col("treatment").is_not_null())
            .sort(["sensor_id", "timestamp"]))
    palette = {"swale": "#1f77b4", "control": "#d62728"}
    for sid, g in sm.group_by("sensor_id"):
        treat = g["treatment"][0]
        ax_sm.plot(g["timestamp"].to_numpy(), g["value"].to_numpy(),
                    color=palette.get(treat, "k"), lw=0.6, alpha=0.6)

    for s, e in zip(soil_events["start"].to_numpy(),
                     soil_events["end"].to_numpy()):
        ax_sm.axvspan(s, e, color="#2ca02c", alpha=0.15)
    ax_sm.set_ylabel(f"VWC at {DETECTION_DEPTH_CM} cm\n(m³/m³)", fontsize=9)

    # --- Onset rug: gauge events (top tick) vs soil events (bottom tick)
    ax_rug.set_ylim(-1, 1)
    if not gauge_events.is_empty():
        ax_rug.vlines(gauge_events["start"].to_numpy(), 0.05, 0.95,
                       color="#1f77b4", lw=0.8, label="Gauge events")
    ax_rug.vlines(soil_events["start"].to_numpy(), -0.95, -0.05,
                   color="#2ca02c", lw=0.8, label="Soil-derived events")
    ax_rug.axhline(0, color="k", lw=0.3, alpha=0.3)
    ax_rug.axvline(GAUGE_VALID_END, color="k", ls=":", lw=0.8, alpha=0.6)
    ax_rug.set_yticks([])
    ax_rug.legend(loc="upper left", fontsize=8, ncol=2)

    # X formatting (manual rotation — autofmt_xdate trips on ns datetimes)
    ax_rug.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax_rug.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in ax_rug.get_xticklabels():
        label.set_rotation(30)
        label.set_horizontalalignment("right")

    fig.suptitle("Soil-derived event detector — validation against rain gauge",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    traces = collect_shallow_traces(df, DETECTION_DEPTH_CM)
    print(f"Detecting on {len(traces)} sensors at {DETECTION_DEPTH_CM} cm: "
          f"{', '.join(sorted(traces.keys()))}")

    soil_events = detect_events(traces, config=DETECTOR)
    print(f"  → {soil_events.height} soil-derived events")

    gauge_events = load_gauge_events()
    print(f"  → {gauge_events.height} gauge-derived events on file")

    # Validate over the gauge-valid period only. Sweep the gauge total_mm
    # threshold so we can see how recall improves once we restrict to events
    # that actually move the soil — sub-2 mm tips often don't.
    gauge_window = gauge_events.filter(pl.col("end") <= GAUGE_VALID_END)
    soil_window  = soil_events.filter(pl.col("end") <= GAUGE_VALID_END)
    print(f"\nValidation (start..{GAUGE_VALID_END:%Y-%m-%d %H:%M}, "
          f"±{MATCH_TOLERANCE_HOURS:g} h tolerance):")
    print(f"  soil events in window: {soil_window.height}")
    print(f"  {'gauge ≥ mm':>12} {'n_gauge':>8} {'TP':>4} {'FP':>4} "
          f"{'FN':>4} {'prec':>5} {'rec':>5} {'f1':>5}")
    for thresh in (0, 2, 5, 10, 20):
        gw = gauge_window.filter(pl.col("total_mm") >= thresh)
        s = match_events(soil_window, gw, tolerance_hours=MATCH_TOLERANCE_HOURS)
        print(f"  {thresh:>12} {gw.height:>8} {s['tp']:>4} {s['fp']:>4} "
              f"{s['fn']:>4} {s['precision']:>5.2f} {s['recall']:>5.2f} "
              f"{s['f1']:>5.2f}")

    # Post-failure events (the actual reason this detector exists).
    post = soil_events.filter(pl.col("start") > GAUGE_VALID_END)
    print(f"\nPost-gauge-failure soil events: {post.height} "
          f"(span {post['start'].min() if not post.is_empty() else 'n/a'} "
          f"… {post['end'].max() if not post.is_empty() else 'n/a'})")

    soil_events.write_csv(SOIL_EVENTS_CSV)
    print(f"\nWrote {SOIL_EVENTS_CSV.relative_to(ROOT)}")

    make_validation_plot(df, soil_events, gauge_events, VALIDATION_PNG)
    print(f"Wrote {VALIDATION_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
