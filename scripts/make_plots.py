"""Quick exploratory plots over the consolidated swale dataset.

Run from the project root::

    PYTHONPATH=src python3 scripts/make_plots.py

Two figures land in plots/:

  weather.png : Precipitation (daily total), air temperature, relative
                humidity, atmospheric pressure — all from logger 19570
                (Top of Swale).
  soil.png    : Soil moisture, soil temperature, bulk EC, faceted by
                depth (rows) and colored by treatment (swale vs control).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

from swale.loader import load_swale_dataset

# Project layout
ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("/home/alexis/DATA/swale")
METADATA = DATA_ROOT / "Metadata.xlsx"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

# Treatment palette (consistent across figures).
COLOR = {"swale": "#1f77b4", "control": "#d62728"}


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
                 ("bulk_ec", "Bulk EC (mS/cm)")]

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

    weather_path = PLOTS / "weather.png"
    soil_path = PLOTS / "soil.png"
    print(f"Plotting weather → {weather_path}")
    plot_weather(df, weather_path)
    print(f"Plotting soil    → {soil_path}")
    plot_soil(df, soil_path)
    print("Done.")


if __name__ == "__main__":
    main()
