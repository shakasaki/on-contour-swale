"""Per-location VWC time series, one figure per depth.

Replaces the pooled-by-treatment view of 01_data_quality with a
spatially-indexed view: 5 swale rows (Top slope -> Step -> Mound ->
Bottom slope 1 -> Bottom slope 2) and 3 control rows (Top -> Mid ->
Bottom), in along-the-slope order, each showing the volumetric water
content trace for a single sensor.

The original Widmer naming convention is preserved. We map each
location to the SMS IDs by depth using ``swale.sites``. The Mound
location has three sensors: SMS 3 at -10 cm (above ground, dropped
from the 10 cm figure), SMS 4 at 10 cm, SMS 5 at 40 cm. The Step
location has only a 40 cm sensor (SMS 10) - the 10 cm row stays in
the figure but reports no data.

Outputs:
  * plots/10_per_location_vwc_10cm.png
  * plots/10_per_location_vwc_40cm.png

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/10_per_location_vwc.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

from swale.config import apply_equilibration_cutoff, load_settings
from swale.loader import load_swale_dataset

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

OUT_10CM = PLOTS / "10_per_location_vwc_10cm.png"
OUT_40CM = PLOTS / "10_per_location_vwc_40cm.png"

# Along-the-slope ordering (top of slope at top of figure for each treatment).
# Each entry: (treatment, widmer_location, sensor_id_by_depth_cm).
# Missing sensors are recorded as None.
LOCATION_ORDER: list[tuple[str, str, dict[int, str | None]]] = [
    ("swale",   "Top slope",      {10: "SMS01", 40: "SMS02"}),
    ("swale",   "Step",           {10: None,    40: "SMS10"}),
    ("swale",   "Mound",          {10: "SMS04", 40: "SMS05"}),
    ("swale",   "Bottom slope 1", {10: "SMS06", 40: "SMS07"}),
    ("swale",   "Bottom slope 2", {10: "SMS08", 40: "SMS09"}),
    ("control", "Top slope",      {10: "SMS11", 40: "SMS12"}),
    ("control", "Mid slope",      {10: "SMS13", 40: "SMS14"}),
    ("control", "Bottom slope",   {10: "SMS15", 40: "SMS16"}),
]

# Visual tunables
FIGSIZE = (14, 10)
LINE_KW = {"lw": 0.7, "alpha": 0.9}
TREATMENT_COLOR = SETTINGS.treatment_colors  # {"swale": "...", "control": "..."}
RAIN_GAUGE_FAILED = SETTINGS.rain_gauge_valid_until


def load_moisture() -> pl.DataFrame:
    """Cached swale dataset filtered to moisture, with equilibration applied."""
    df = load_swale_dataset(
        data_root=DATA_ROOT, metadata_xlsx=METADATA,
        cache_dir=CACHE, grid="none",
    )
    df = apply_equilibration_cutoff(df, SETTINGS)
    return df.filter(pl.col("variable") == "moisture").sort("timestamp")


def plot_one_depth(df: pl.DataFrame, depth_cm: int, out: Path) -> None:
    """Render the 8-row figure for a single depth."""
    n_rows = len(LOCATION_ORDER)
    fig, axes = plt.subplots(
        n_rows, 1, figsize=FIGSIZE, sharex=True, constrained_layout=True,
    )
    if n_rows == 1:
        axes = [axes]

    # Common time range from the loaded data
    t_min = df["timestamp"].min()
    t_max = df["timestamp"].max()

    # Common VWC y-axis range across all panels (so we can compare visually)
    # but allow a small margin so peaks aren't clipped.
    vwc_max = float(df["value"].max())
    vwc_min = float(df["value"].min())
    margin = 0.02
    y_lo = max(0.0, vwc_min - margin)
    y_hi = vwc_max + margin

    for ax, (treatment, location, sensor_by_depth) in zip(axes, LOCATION_ORDER):
        sid = sensor_by_depth.get(depth_cm)
        color = TREATMENT_COLOR.get(treatment, "black")

        if sid is None:
            ax.text(
                0.5, 0.5,
                f"no {depth_cm} cm sensor at {treatment} {location}",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=9, color="grey", style="italic",
            )
        else:
            sub = df.filter(pl.col("sensor_id") == sid)
            if sub.is_empty():
                ax.text(
                    0.5, 0.5, f"no data for {sid}",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=9, color="grey", style="italic",
                )
            else:
                ax.plot(
                    sub["timestamp"], sub["value"],
                    color=color, label=sid, **LINE_KW,
                )

        # Mark rain-gauge failure for context
        if RAIN_GAUGE_FAILED:
            ax.axvline(
                dt.datetime.fromisoformat(RAIN_GAUGE_FAILED),
                color="black", ls=":", lw=0.7, alpha=0.4,
            )

        # Row label inside the axis on the right (compact)
        ax.text(
            1.005, 0.5,
            f"{treatment} {location}\n{sid or '-'}",
            transform=ax.transAxes, ha="left", va="center", fontsize=9,
            color=color, weight="bold",
        )
        ax.set_ylim(y_lo, y_hi)
        ax.set_ylabel("VWC")
        ax.grid(alpha=0.25)

    axes[-1].set_xlabel("Date")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()

    fig.suptitle(
        f"Per-location VWC at {depth_cm} cm depth\n"
        f"Top-to-bottom = along slope; swale ({TREATMENT_COLOR['swale']}) then "
        f"control ({TREATMENT_COLOR['control']}); dotted line = rain gauge silent "
        f"({RAIN_GAUGE_FAILED})",
        fontsize=11, weight="bold",
    )
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out.relative_to(ROOT)}")


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print("Loading dataset (cached) ...")
    df = load_moisture()
    print(f"  {df.height:,} moisture rows  "
          f"({df['timestamp'].min()} -> {df['timestamp'].max()})")

    for depth, out in ((10, OUT_10CM), (40, OUT_40CM)):
        print(f"Rendering {depth} cm panel ...")
        plot_one_depth(df, depth, out)


if __name__ == "__main__":
    main()
