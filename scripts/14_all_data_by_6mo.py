"""Full-record overview: every variable plotted in consecutive 6-month
windows, split by data type.

For each 6-month window since the first reading in the dataset, and for each
of three data-type groups (soil / weather / housekeeping), one figure is
written with one row per variable. Each series is drawn as an **hourly mean
line with an hourly min–max shaded band**, so both the trend and the spread
within each hour are visible at this zoom level.

Flagged readings (METER ``error_code`` != 0 — e.g. the dead ``sw_b2_40``
probe) are nulled out before aggregation so bogus 0.0 values don't wreck the
y-scale. Gaps show as breaks in the line.

Run from the project root::

    conda run -n swale python scripts/14_all_data_by_6mo.py

Outputs (3 groups x N windows) in ``plots/``::

    allrange_soil_01_202405-202411.png
    allrange_weather_01_202405-202411.png
    allrange_housekeeping_01_202405-202411.png
    ...
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

from swale.config import load_settings
from swale.display_names import display
from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

WINDOW_MONTHS = 6
AGG = "1h"                      # aggregation bucket for the mean + min/max band
BAND_ALPHA = 0.18
LINE_KW = dict(lw=0.8)

TREATMENT_COLOR = dict(SETTINGS.treatment_colors)   # swale / control
DEPTH_STYLE = {10: "-", 40: "--", -10: ":"}         # soil linestyle by depth
LOGGER_COLOR = {"05511": "#d62728", "19570": "#1f77b4", "19574": "#2ca02c"}

# variable -> (row label incl. unit). Order within each group is the plot order.
GROUPS: dict[str, list[str]] = {
    "soil": ["moisture", "soil_temp", "sat_extract_ec", "bulk_ec"],
    "weather": ["precipitation", "max_precip_rate", "air_temp",
                "humidity", "vpd", "vapor_pressure", "atm_pressure"],
    "housekeeping": ["battery_pct", "battery_mv", "ref_pressure", "logger_temp"],
}

VAR_LABEL = {
    "moisture": "VWC (m³/m³)",
    "soil_temp": "Soil temp (°C)",
    "sat_extract_ec": "Sat. extract EC (mS/cm)",
    "bulk_ec": "Bulk EC (mS/cm)",
    "precipitation": "Precip (mm/h)",
    "max_precip_rate": "Max precip rate (mm/h)",
    "air_temp": "Air temp (°C)",
    "humidity": "RH (%)",
    "vpd": "VPD (kPa)",
    "vapor_pressure": "Vapor press. (kPa)",
    "atm_pressure": "Atm press. (kPa)",
    "battery_pct": "Battery (%)",
    "battery_mv": "Battery (mV)",
    "ref_pressure": "Ref press. (kPa)",
    "logger_temp": "Logger temp (°C)",
}

# Precipitation is a per-interval accumulation: sum it per bucket, no band.
SUM_VARS = {"precipitation"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_months(d: date, n: int) -> date:
    """First-of-implementation month arithmetic; day is preserved (always 1–28
    here so no clamping needed)."""
    m0 = d.month - 1 + n
    return date(d.year + m0 // 12, m0 % 12 + 1, d.day)


def windows(t_min: datetime, t_max: datetime) -> list[tuple[datetime, datetime]]:
    """Consecutive [start, end) 6-month spans covering [t_min, t_max]."""
    start = datetime(t_min.year, t_min.month, t_min.day)
    out: list[tuple[datetime, datetime]] = []
    while start <= t_max:
        end = datetime.combine(add_months(start.date(), WINDOW_MONTHS),
                               datetime.min.time())
        out.append((start, end))
        start = end
    return out


def null_flagged(df: pl.DataFrame) -> pl.DataFrame:
    """Set value -> null wherever error_code is non-zero."""
    return df.with_columns(
        pl.when(pl.col("error_code").fill_null(0) != 0)
          .then(None)
          .otherwise(pl.col("value"))
          .alias("value")
    )


def bucket_stats(df: pl.DataFrame, variable: str) -> pl.DataFrame:
    """(key_col, ts, mean, lo, hi) per bucket, where key_col groups the lines
    on the axis: sensor_id for soil/weather, logger_serial for housekeeping."""
    f = (df.filter((pl.col("variable") == variable)
                   & pl.col("value").is_not_null())
           .with_columns(pl.col("timestamp").dt.truncate(AGG).alias("ts")))
    if f.height == 0:
        return f.select("sensor_id", "ts").head(0)

    key = "logger_serial" if variable in GROUPS["housekeeping"] else "sensor_id"
    if variable in SUM_VARS:
        return (f.group_by(key, "ts")
                 .agg(pl.col("value").sum().alias("mean"))
                 .with_columns(lo=pl.col("mean"), hi=pl.col("mean"))
                 .rename({key: "grp"})
                 .sort("grp", "ts"))
    return (f.group_by(key, "ts")
             .agg(pl.col("value").mean().alias("mean"),
                  pl.col("value").min().alias("lo"),
                  pl.col("value").max().alias("hi"))
             .rename({key: "grp"})
             .sort("grp", "ts"))


def series_style(group: str, grp_key: str, meta: dict) -> tuple[dict, str]:
    """Return (matplotlib kwargs, legend label) for one series."""
    if group == "housekeeping":
        return (dict(color=LOGGER_COLOR.get(grp_key, "#333"), **LINE_KW),
                f"z6-{grp_key}")
    if group == "weather":
        return dict(color="#333333", **LINE_KW), grp_key
    # soil
    m = meta.get(grp_key, {})
    treatment, depth = m.get("treatment"), m.get("depth_cm")
    color = TREATMENT_COLOR.get(treatment, "#777777")
    ls = DEPTH_STYLE.get(depth, "-")
    return dict(color=color, linestyle=ls, **LINE_KW), display(grp_key)


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_group_window(df_win: pl.DataFrame, group: str, variables: list[str],
                      w_start: datetime, w_end: datetime, idx: int,
                      soil_meta: dict) -> Path | None:
    present = [v for v in variables
              if df_win.filter((pl.col("variable") == v)
                               & pl.col("value").is_not_null()).height > 0]
    if not present:
        return None

    fig, axes = plt.subplots(len(present), 1, figsize=(13, 2.3 * len(present)),
                             sharex=True, squeeze=False)
    axes = axes[:, 0]

    for ax, var in zip(axes, present):
        stats = bucket_stats(df_win, var)
        for grp_key, sub in stats.group_by("grp", maintain_order=True):
            grp_key = grp_key[0] if isinstance(grp_key, tuple) else grp_key
            kw, label = series_style(group, grp_key, soil_meta)
            ts = sub["ts"].to_list()
            ax.plot(ts, sub["mean"].to_list(), label=label, **kw)
            if var not in SUM_VARS:
                ax.fill_between(ts, sub["lo"].to_list(), sub["hi"].to_list(),
                                color=kw["color"], alpha=BAND_ALPHA, lw=0)
        ax.set_ylabel(VAR_LABEL.get(var, var), fontsize=9)
        ax.grid(alpha=0.25, lw=0.5)
        ax.margins(x=0)

    # One legend for the whole figure (dedup labels).
    handles, labels = [], []
    for ax in axes:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h); labels.append(l)
    ncol = min(len(labels), 8)
    fig.legend(handles, labels, loc="upper center", ncol=ncol, fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, 1.0))

    axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator())
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(
        axes[-1].xaxis.get_major_locator()))
    axes[-1].set_xlim(w_start, w_end)

    fig.suptitle(
        f"{group.capitalize()} — {w_start:%Y-%m-%d} to {w_end:%Y-%m-%d} "
        f"(hourly mean, band = hourly min–max; flagged readings removed)",
        y=1.005, fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    out = PLOTS / (f"allrange_{group}_{idx:02d}_"
                   f"{w_start:%Y%m}-{w_end:%Y%m}.png")
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print("Loading dataset…")
    df = load_swale_dataset(data_root=DATA_ROOT, metadata_xlsx=METADATA,
                            cache_dir=CACHE, grid="none")
    df = null_flagged(df)

    soil_meta = {
        r["sensor_id"]: {"treatment": r["treatment"], "depth_cm": r["depth_cm"]}
        for r in df.filter(pl.col("sensor_type") == "TEROS12")
                   .select("sensor_id", "treatment", "depth_cm")
                   .unique().to_dicts()
    }

    t_min, t_max = df["timestamp"].min(), df["timestamp"].max()
    wins = windows(t_min, t_max)
    print(f"  {df.height:,} rows, {t_min:%Y-%m-%d} → {t_max:%Y-%m-%d}, "
          f"{len(wins)} six-month windows")

    written = 0
    for idx, (w0, w1) in enumerate(wins, start=1):
        df_win = df.filter((pl.col("timestamp") >= w0)
                           & (pl.col("timestamp") < w1))
        if df_win.height == 0:
            continue
        for group, variables in GROUPS.items():
            out = plot_group_window(df_win, group, variables, w0, w1, idx,
                                    soil_meta)
            if out is not None:
                print(f"  → {out.relative_to(ROOT)}")
                written += 1
    print(f"done ({written} figures)")


if __name__ == "__main__":
    main()
