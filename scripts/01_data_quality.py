"""Data-quality overview + sensor equilibration diagnostics.

Run from the project root::

    PYTHONPATH=src python3 scripts/01_data_quality.py

Outputs in plots/:

  01_weather.png        : Precipitation (daily total), air temperature, RH,
                          atmospheric pressure — all from logger 19570.
  01_soil.png           : Soil moisture, soil temperature, bulk EC, faceted
                          by depth (rows) × treatment (color).
  01_equilibration.png  : Per-sensor first-N-days view (cutoff line drawn
                          at ``equilibration.days_default`` from settings),
                          one row per sensor, columns = variables.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

from swale.config import load_settings, per_sensor_first_valid
from swale.loader import load_swale_dataset

# Project layout
ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

# Treatment palette (consistent across figures). From settings.
COLOR = dict(SETTINGS.treatment_colors)

# How many days past first_valid to show in the equilibration figure (wider
# than the cutoff so you can see the settling and a few days of post-cutoff
# steady state side-by-side).
EQUILIBRATION_PLOT_DAYS = SETTINGS.equilibration.days_default + 7


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def hourly_mean(df: pl.DataFrame, variable: str,
                  sensor_id: str | None = None) -> pl.DataFrame:
    """Return a (timestamp, value) frame at hourly cadence."""
    f = df.filter((pl.col("variable") == variable)
                   & pl.col("value").is_not_null())
    if sensor_id is not None:
        f = f.filter(pl.col("sensor_id") == sensor_id)
    return (f.with_columns(pl.col("timestamp").dt.truncate("1h").alias("ts"))
              .group_by("ts").agg(pl.col("value").mean())
              .sort("ts"))


def daily_sum(df: pl.DataFrame, variable: str,
                sensor_id: str | None = None) -> pl.DataFrame:
    f = df.filter((pl.col("variable") == variable)
                   & pl.col("value").is_not_null())
    if sensor_id is not None:
        f = f.filter(pl.col("sensor_id") == sensor_id)
    return (f.with_columns(pl.col("timestamp").dt.date().alias("date"))
              .group_by("date").agg(pl.col("value").sum())
              .sort("date"))


# ---------------------------------------------------------------------------
# Weather figure
# ---------------------------------------------------------------------------

def plot_weather(df: pl.DataFrame, out: Path) -> None:
    # Drop sensor-startup junk: a few near-zero readings on atm_pressure
    # appear at first power-on. Filter them so the plot scales sensibly.
    weather = df.filter(
        (pl.col("logger_serial") == "19570")
        & ~((pl.col("variable") == "atm_pressure") & (pl.col("value") < 50))
        & ~((pl.col("variable") == "humidity") & (pl.col("value") < 0.01))
        & ~((pl.col("variable") == "air_temp") & (pl.col("value") < 0))
    )

    fig, axes = plt.subplots(4, 1, figsize=(12, 9), sharex=True)
    fig.suptitle("Weather at the Top-of-Swale logger (19570)", fontsize=14,
                  weight="bold")

    # Precipitation: daily totals
    rain = daily_sum(weather, "precipitation")
    ax = axes[0]
    ax.bar(rain["date"].to_list(), rain["value"].to_list(),
            color="#1f77b4", width=1.0)
    ax.set_ylabel("Rain (mm/day)")
    ax.grid(alpha=0.3)

    # Air temperature: hourly mean
    air = hourly_mean(weather, "air_temp")
    ax = axes[1]
    ax.plot(air["ts"].to_list(), air["value"].to_list(),
             color="#d62728", linewidth=0.6)
    ax.set_ylabel("Air temp (°C)")
    ax.grid(alpha=0.3)

    # Relative humidity: hourly mean (xlsx only — coverage ends Feb 2025)
    rh = hourly_mean(weather, "humidity")
    ax = axes[2]
    if rh.height:
        ax.plot(rh["ts"].to_list(), rh["value"].to_list(),
                 color="#2ca02c", linewidth=0.6)
        ax.set_ylabel("RH (%)")
    else:
        ax.text(0.5, 0.5, "No humidity data", ha="center", va="center",
                transform=ax.transAxes)
        ax.set_ylabel("RH (%)")
    ax.grid(alpha=0.3)

    # Atmospheric pressure: zoom y-axis to the actual data range, otherwise
    # the variation gets squashed near a 0-kPa baseline.
    p = hourly_mean(weather, "atm_pressure")
    ax = axes[3]
    ax.plot(p["ts"].to_list(), p["value"].to_list(),
             color="#9467bd", linewidth=0.6)
    ax.set_ylabel("Atm. pressure (kPa)")
    if p.height:
        lo = p["value"].quantile(0.001)
        hi = p["value"].quantile(0.999)
        pad = max(0.1, (hi - lo) * 0.1)
        ax.set_ylim(lo - pad, hi + pad)
    ax.grid(alpha=0.3)

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].set_xlabel("date")
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Soil figure
# ---------------------------------------------------------------------------

# What depths to facet on, and how to label them.
DEPTH_FACETS: list[tuple[object, str]] = [
    (-10, "Above ground (-10 cm, on mound)"),
    (10,  "Topsoil (10 cm)"),
    (40,  "Subsoil (40 cm)"),
    (None, "Control rows (depth unrecorded)"),
]


def plot_soil(df: pl.DataFrame, out: Path) -> None:
    """Soil moisture / temperature / bulk EC, faceted by depth × treatment."""
    soil = df.filter(pl.col("sensor_type") == "TEROS12")

    variables = [("moisture", "Soil moisture (m³/m³)"),
                 ("soil_temp", "Soil temperature (°C)"),
                 ("sat_extract_ec", "Sat. extract EC (mS/cm)")]

    fig, axes = plt.subplots(len(DEPTH_FACETS), len(variables),
                              figsize=(15, 10), sharex=True)
    fig.suptitle("Soil sensors by depth × treatment", fontsize=14, weight="bold")

    for col_i, (var, ylabel) in enumerate(variables):
        v = soil.filter(pl.col("variable") == var)
        for row_i, (depth, depth_label) in enumerate(DEPTH_FACETS):
            ax = axes[row_i, col_i]
            if depth is None:
                bucket = v.filter(pl.col("depth_cm").is_null()
                                   & pl.col("treatment").is_not_null())
            else:
                bucket = v.filter(pl.col("depth_cm") == depth)

            seen_treatments: set[str] = set()
            for sensor_id, group in (bucket.sort("timestamp")
                                            .group_by("sensor_id",
                                                      maintain_order=True)):
                sensor_id = sensor_id[0] if isinstance(sensor_id, tuple) else sensor_id
                treatment = group["treatment"].drop_nulls().first()
                if treatment is None:
                    continue
                hourly = (group.with_columns(pl.col("timestamp")
                                                .dt.truncate("1h")
                                                .alias("ts"))
                                .group_by("ts").agg(pl.col("value").mean())
                                .sort("ts"))
                # Show treatment in the legend only once per panel,
                # regardless of how many sensors are at this depth.
                label = treatment if treatment not in seen_treatments else None
                seen_treatments.add(treatment)
                ax.plot(hourly["ts"].to_list(),
                         hourly["value"].to_list(),
                         color=COLOR.get(treatment, "#888"),
                         linewidth=0.5,
                         alpha=0.8,
                         label=label)

            if row_i == 0:
                ax.set_title(ylabel, fontsize=11, weight="bold")
            if col_i == 0:
                ax.set_ylabel(depth_label, fontsize=10)
            ax.grid(alpha=0.3)
            if seen_treatments:
                ax.legend(fontsize=9, loc="best")

    axes[-1, 0].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    axes[-1, 0].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Equilibration figure
# ---------------------------------------------------------------------------

EQUILIBRATION_VARIABLES: list[tuple[str, str]] = [
    ("moisture",  "VWC (m³/m³)"),
    ("soil_temp", "Soil temp (°C)"),
    ("sat_extract_ec", "Sat. extract EC (mS/cm)"),
]


def plot_equilibration(df: pl.DataFrame, out: Path) -> None:
    """Per-sensor first-N-days panel grid with the equilibration cutoff drawn.

    Rows: TEROS12 sensors sorted by ``sensor_id``. Columns: variables in
    ``EQUILIBRATION_VARIABLES``. Each panel plots raw values for the first
    ``EQUILIBRATION_PLOT_DAYS`` after that sensor's first non-null reading,
    with a vertical dashed line at the equilibration cutoff
    (``first_valid + equilibration.days_for(sensor)``). Useful for sanity-
    checking whether the chosen cutoff actually removes the settling
    transient for each channel.
    """
    # SMS-prefix filter: the cache has a pre-existing tagging anomaly where
    # ATMOS14_19570 has a few rows mislabelled as TEROS12. Stick to the soil-
    # moisture sensors by ID prefix and the figure stays clean regardless.
    soil = df.filter(
        (pl.col("sensor_type") == "TEROS12")
        & pl.col("sensor_id").str.starts_with("SMS")
    )
    fv = per_sensor_first_valid(soil).sort("sensor_id")
    sensor_ids = fv["sensor_id"].to_list()
    if not sensor_ids:
        return

    n_rows = len(sensor_ids)
    n_cols = len(EQUILIBRATION_VARIABLES)
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(3.5 * n_cols, 1.5 * n_rows),
        sharex=False,
    )
    if n_rows == 1:
        axes = axes.reshape(1, -1)

    fv_map = dict(zip(fv["sensor_id"].to_list(), fv["first_valid"].to_list()))

    for row_i, sensor_id in enumerate(sensor_ids):
        t0 = fv_map[sensor_id]
        t_end = t0 + timedelta(days=EQUILIBRATION_PLOT_DAYS)
        cutoff_days = SETTINGS.equilibration.days_for(sensor_id)
        t_cut = t0 + timedelta(days=cutoff_days)
        sensor_rows = soil.filter(
            (pl.col("sensor_id") == sensor_id)
            & (pl.col("timestamp") >= t0)
            & (pl.col("timestamp") < t_end)
        )
        treatment = sensor_rows["treatment"].drop_nulls().first() if sensor_rows.height else None
        color = COLOR.get(treatment, "#444")

        for col_i, (var, ylabel) in enumerate(EQUILIBRATION_VARIABLES):
            ax = axes[row_i, col_i]
            sub = (sensor_rows
                   .filter(pl.col("variable") == var)
                   .sort("timestamp"))
            if sub.height:
                ax.plot(sub["timestamp"].to_list(), sub["value"].to_list(),
                        color=color, linewidth=0.6)
            ax.axvline(t_cut, color="black", linestyle="--", linewidth=0.8,
                       alpha=0.7)
            ax.set_xlim(t0, t_end)
            if col_i == 0:
                ax.set_ylabel(f"{sensor_id}\n({treatment or '?'})", fontsize=8)
            if row_i == 0:
                ax.set_title(ylabel, fontsize=10, weight="bold")
            ax.tick_params(axis="both", labelsize=7)
            ax.grid(alpha=0.25)

        # Only label x-axis ticks on the bottom row.
        for col_i in range(n_cols):
            if row_i == n_rows - 1:
                axes[row_i, col_i].xaxis.set_major_locator(mdates.DayLocator(interval=5))
                axes[row_i, col_i].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            else:
                axes[row_i, col_i].set_xticklabels([])

    fig.suptitle(
        f"Sensor equilibration ({EQUILIBRATION_PLOT_DAYS} days from first reading; "
        f"dashed line = equilibration cutoff at {SETTINGS.equilibration.days_default} d)",
        fontsize=12, weight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print(f"Equilibration default: {SETTINGS.equilibration.days_default} d "
          f"(overrides for {len(SETTINGS.equilibration.days_overrides)} sensors)")
    print("Loading dataset (cached if available)…")
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )
    print(f"  {df.height:,} rows")

    weather_path = PLOTS / "01_weather.png"
    soil_path    = PLOTS / "01_soil.png"
    eq_path      = PLOTS / "01_equilibration.png"
    print(f"Plotting weather       → {weather_path}")
    plot_weather(df, weather_path)
    print(f"Plotting soil          → {soil_path}")
    plot_soil(df, soil_path)
    print(f"Plotting equilibration → {eq_path}")
    plot_equilibration(df, eq_path)
    print("Done.")


if __name__ == "__main__":
    main()
