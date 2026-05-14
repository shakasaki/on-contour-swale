"""Diagnostic plots to investigate suspected discontinuities in the dataset.

Overlay each sensor's time-series with the data source colour-coded:
  - XLSX-sourced rows in one colour
  - CSV-sourced rows in another

If a visible step change in the value lines up with a colour change, the
'jump' is an artefact of the source-switch (most likely the
Saturation-Extract-EC vs Bulk-EC quantity mismatch on the EC channel)
rather than a real environmental signal.

Also produces a small CSV report with the value gap at every source
boundary (the median delta between the last 24 hours of XLSX data and
the first 24 hours of CSV data per (sensor, variable)).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import polars as pl

from swale.config import load_settings
from swale.loader import load_swale_dataset

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

SOURCE_COLOR = {"xlsx": "#1f77b4", "csv": "#d62728"}


def hourly_with_source(df: pl.DataFrame) -> pl.DataFrame:
    """Hourly mean per (sensor_id, variable, source_format)."""
    return (
        df.filter(pl.col("value").is_not_null())
          .with_columns(pl.col("timestamp").dt.truncate("1h").alias("ts"))
          .group_by(["sensor_id", "variable", "source_format", "ts"])
          .agg(pl.col("value").mean())
          .sort(["sensor_id", "variable", "ts"])
    )


def boundary_report(df: pl.DataFrame) -> pl.DataFrame:
    """Per (sensor, variable): median value in the last day of XLSX vs the first day of CSV.

    Reveals which channels show a step change at the source-switch boundary.
    """
    rows = []
    for (sensor_id, variable), grp in (
        df.filter(pl.col("value").is_not_null())
          .group_by(["sensor_id", "variable"])
    ):
        sensor_id = sensor_id[0] if isinstance(sensor_id, tuple) else sensor_id
        variable = variable[0] if isinstance(variable, tuple) else variable
        x = grp.filter(pl.col("source_format") == "xlsx")
        c = grp.filter(pl.col("source_format") == "csv")
        if x.height == 0 or c.height == 0:
            continue
        boundary = x["timestamp"].max()
        if boundary is None:
            continue
        last_xlsx = x.filter(pl.col("timestamp") >= boundary - timedelta(days=1))
        first_csv = c.filter(pl.col("timestamp") <= boundary + timedelta(days=1))
        if last_xlsx.height == 0 or first_csv.height == 0:
            continue
        rows.append({
            "sensor_id": sensor_id,
            "variable": variable,
            "boundary": boundary,
            "n_xlsx_24h": last_xlsx.height,
            "n_csv_24h": first_csv.height,
            "med_xlsx": float(last_xlsx["value"].median()),
            "med_csv": float(first_csv["value"].median()),
            "delta": float(first_csv["value"].median()
                            - last_xlsx["value"].median()),
        })
    if not rows:
        return pl.DataFrame()
    return (pl.DataFrame(rows)
              .sort([(pl.col("delta").abs())], descending=True)
              .with_columns(pl.col("delta").round(4)))


def plot_source_overlay(df: pl.DataFrame, *, variable: str, out: Path) -> None:
    """One panel per sensor; lines coloured by source_format."""
    sub = df.filter(pl.col("variable") == variable)
    if sub.height == 0:
        return
    sensors = sorted(sub["sensor_id"].unique().to_list())

    n = len(sensors)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 2.5 * nrows),
                              sharex=True, sharey=True)
    fig.suptitle(f"{variable} — coloured by source format "
                  f"(blue=XLSX, red=CSV). A step at the colour boundary "
                  f"is a source-switching artefact.",
                  fontsize=11, weight="bold")

    axes_flat = axes.flatten() if nrows > 1 else [axes] if ncols == 1 else axes

    hourly = hourly_with_source(sub)

    for ax, sensor_id in zip(axes_flat, sensors):
        s = hourly.filter(pl.col("sensor_id") == sensor_id)
        for src, color in SOURCE_COLOR.items():
            piece = s.filter(pl.col("source_format") == src).sort("ts")
            if piece.height == 0:
                continue
            ax.plot(piece["ts"].to_list(), piece["value"].to_list(),
                     color=color, linewidth=0.6, label=src)
        meta = sub.filter(pl.col("sensor_id") == sensor_id).head(1)
        if meta.height:
            tr = meta["treatment"].item() or "?"
            depth = meta["depth_cm"].item()
            depth_s = f"{depth} cm" if depth is not None else "depth ?"
            ax.set_title(f"{sensor_id} — {tr}, {depth_s}", fontsize=9)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="lower right")

    # Hide unused subplots
    for ax in axes_flat[n:]:
        ax.set_visible(False)

    for ax in axes[-1, :] if nrows > 1 else [axes_flat[-1]]:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )

    soil = df.filter(pl.col("sensor_type") == "TEROS12")

    # Plots
    for var in ("bulk_ec", "moisture", "soil_temp"):
        out = PLOTS / f"diag_{var}.png"
        print(f"  -> {out}")
        plot_source_overlay(soil, variable=var, out=out)

    # Boundary table
    print("\n=== boundary report (top deltas at XLSX->CSV transition) ===")
    rep = boundary_report(soil)
    if rep.height:
        with pl.Config(tbl_rows=30, tbl_width_chars=160):
            print(rep)
        rep_path = PLOTS / "boundary_report.csv"
        rep.write_csv(rep_path)
        print(f"saved -> {rep_path}")


if __name__ == "__main__":
    main()
