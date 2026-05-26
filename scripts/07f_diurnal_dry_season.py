"""Diurnal cycle of VWC at swale Mound vs control Mid during the dry
season — at both 10 cm and 40 cm.

Hypothesis: trees planted on the swale Mound transpire water that the
rooting zone supplies, producing a daytime drawdown / nighttime
partial recovery in VWC at the Mound.  The control mid-slope plot
(no trees on the strip) should show no such signature.

Methodology (corrected)
-----------------------
Earlier version used per-calendar-day mean subtraction.  That contains
a bug when the soil dries within the day: the residual contains the
within-day secular drift on top of the real diurnal cycle, and for
fast-drying sensors the drift dominates and produces an apparent
"cycle" that looks like a sawtooth (high at 00:00, low at 23:00).
SMS05 dries ~0.0013 m³/m³ per day in the dry season → its apparent
cycle was just the drift.

Corrected approach:
1. **High-pass at 24 h**: subtract a 24-h centered running mean from
   each 5-min reading.  This removes the secular drift entirely and
   keeps only sub-daily variation (true diurnal cycle + noise).
2. Bin residuals by hour-of-day, report median + IQR per hour.
3. Same time window for both sensors; the operation is per-sensor
   on its own time series (sensors are not joined on timestamp —
   each runs independently).

Equivalent to a notch-filter version of the composite-day stack, with
the secular trend properly removed.

Pairs compared
--------------
    SMS04 (swale Mound, 10 cm) vs SMS13 (control Mid, 10 cm)
    SMS05 (swale Mound, 40 cm) vs SMS14 (control Mid, 40 cm)

Windows
-------
Early dry: 2024-12-01 → 2025-01-31
Late  dry: 2025-03-01 → 2025-04-30
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

OUT = Path("plots/07f_diurnal_dry_season.png")

PAIRS = [
    (10, "SMS04", "SMS13"),
    (40, "SMS05", "SMS14"),
]

WINDOWS = [
    ("Early dry — 2024-12 → 2025-01", "2024-12-01", "2025-01-31"),
    ("Late dry — 2025-03 → 2025-04",   "2025-03-01", "2025-04-30"),
]

COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"

# 5-min cadence → 288 samples = 24 h
WINDOW_24H_SAMPLES = 288


def load() -> pl.DataFrame:
    sensors = {sid for _, sw, ct in PAIRS for sid in (sw, ct)}
    files = sorted(Path("cache").glob("logger=*.parquet"))
    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    df = df.filter(pl.col("sensor_id").is_in(list(sensors))
                    & pl.col("variable").is_in(["moisture", "soil_temp"]))
    df = df.filter(~((pl.col("variable") == "moisture") & (pl.col("value") < 0.01)))
    return df


def highpass_diurnal(df: pl.DataFrame, sensor: str, variable: str,
                      start: str, end: str
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (hour, median, q25, q75) deviation after 24-h high-pass.

    Detrending: subtract a 24-h centered rolling mean from each value.
    Removes any signal with period > 24 h (secular drift, multi-day
    fluctuation) and keeps the within-day cycle.
    """
    sub = (df.filter((pl.col("sensor_id") == sensor)
                      & (pl.col("variable") == variable)
                      & (pl.col("timestamp") >= pl.lit(start).str.to_datetime())
                      & (pl.col("timestamp") <  pl.lit(end).str.to_datetime()))
              .sort("timestamp"))
    if sub.height < WINDOW_24H_SAMPLES:
        return (np.arange(24) + 0.5, np.full(24, np.nan),
                np.full(24, np.nan), np.full(24, np.nan))

    sub = sub.with_columns(
        pl.col("value").rolling_mean(WINDOW_24H_SAMPLES, center=True)
                          .alias("trend24h")
    )
    sub = sub.filter(pl.col("trend24h").is_not_null())
    sub = sub.with_columns([
        (pl.col("value") - pl.col("trend24h")).alias("dev"),
        pl.col("timestamp").dt.hour().alias("hour"),
    ])
    per_hour = (sub.group_by("hour").agg([
        pl.col("dev").median().alias("m"),
        pl.col("dev").quantile(0.25).alias("q25"),
        pl.col("dev").quantile(0.75).alias("q75"),
    ]).sort("hour"))

    med = np.full(24, np.nan)
    q25 = np.full(24, np.nan)
    q75 = np.full(24, np.nan)
    for h, m, lo, hi in zip(per_hour["hour"].to_numpy(),
                             per_hour["m"].to_numpy(),
                             per_hour["q25"].to_numpy(),
                             per_hour["q75"].to_numpy()):
        med[int(h)] = m
        q25[int(h)] = lo
        q75[int(h)] = hi
    return np.arange(24) + 0.5, med, q25, q75


def _plot_pair(ax, df, swale_id, ctrl_id, variable, s, e, scale: float,
                ylabel: str):
    for sid, color, lab in [
        (ctrl_id,  COLOR_CTRL,  f"control Mid {display(ctrl_id)}"),
        (swale_id, COLOR_SWALE, f"swale Mound {display(swale_id)}"),
    ]:
        h, med, q25, q75 = highpass_diurnal(df, sid, variable, s, e)
        ax.fill_between(h, q25 * scale, q75 * scale, color=color, alpha=0.15)
        ax.plot(h, med * scale, color=color, linewidth=2.0,
                  marker="o", markersize=3, label=lab)
        if np.isfinite(med).any():
            p2p = float(np.nanmax(med) - np.nanmin(med)) * scale
            y_off = 0.92 if sid == swale_id else 0.84
            ax.text(0.01, y_off, f"{display(sid)} p2p = {p2p:+.3f}",
                      transform=ax.transAxes, color=color, fontsize=8)
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)


def main() -> None:
    df = load()
    fig, axes = plt.subplots(4, 2, figsize=(12, 11), sharex=True)
    # rows = (10 cm VWC, 10 cm T, 40 cm VWC, 40 cm T)
    # cols = (early dry, late dry)
    for col_i, (wlabel, s, e) in enumerate(WINDOWS):
        for pair_i, (depth, swale_id, ctrl_id) in enumerate(PAIRS):
            ax_v = axes[2 * pair_i, col_i]
            _plot_pair(ax_v, df, swale_id, ctrl_id, "moisture", s, e,
                        scale=1000.0,
                        ylabel=f"{depth} cm\nVWC residual\n($10^{{-3}}$ m³/m³)")
            if pair_i == 0:
                ax_v.set_title(wlabel, fontsize=11, weight="bold")

            ax_t = axes[2 * pair_i + 1, col_i]
            _plot_pair(ax_t, df, swale_id, ctrl_id, "soil_temp", s, e,
                        scale=1.0,
                        ylabel=f"{depth} cm\nsoil-T residual\n(°C)")

    axes[-1, 0].set_xlabel("Hour of day (local)")
    axes[-1, 1].set_xlabel("Hour of day (local)")
    for ax in axes[-1]:
        ax.set_xticks(range(0, 25, 3))

    fig.suptitle("Dry-season diurnal cycle (24-h high-passed) — "
                  "Mound vs control Mid, both depths",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
