"""Compare forward vs centered difference for the PET ↔ ΔVWC
regression at Bottom slope 1 (where we have a clean signal).

Forward difference:   dvwc(d) = vwc(d+1) − vwc(d)
Centered difference:  dvwc(d) = (vwc(d+1) − vwc(d−1)) / 2

The centered version is 2nd-order accurate (error O(h²)) vs the
forward (O(h)).  Both should give very similar β for a clean signal;
the centered version should be slightly less biased on noisier data.

We restrict to SMS07 (Bot 1 swale, 40 cm — clean transpiration
signal) and SMS16 (control twin, no signal), both depths, in the
dry-season window 2024-12-01 → 2025-04-30.

Output: plots/07h_centered_vs_forward.png — a single 2×2 figure
(rows = depth, cols = control / swale) overlaying both differencing
schemes with their fits and β values.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

OUT = Path("plots/07h_centered_vs_forward.png")
DRY_START = "2024-12-01"
DRY_END   = "2025-04-30"

PAIRS = [
    (10, "SMS06", "SMS15"),
    (40, "SMS07", "SMS16"),
]
COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"


def load_daily_vwc(sensor: str) -> pl.DataFrame:
    files = sorted(Path("cache").glob("logger=*.parquet"))
    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    df = df.filter((pl.col("sensor_id") == sensor)
                    & (pl.col("variable") == "moisture")
                    & (pl.col("value") > 0.01))
    first = df["timestamp"].min()
    df = df.filter(pl.col("timestamp") >= first + pl.duration(days=14))
    daily = (df.with_columns(pl.col("timestamp").dt.date().alias("date"))
                .group_by("date")
                .agg([pl.col("value").mean().alias("vwc"),
                      pl.col("value").count().alias("n")])
                .filter(pl.col("n") >= 200)
                .sort("date"))
    daily = daily.with_columns([
        (pl.col("vwc").shift(-1) - pl.col("vwc")).alias("dvwc_fwd"),
        ((pl.col("vwc").shift(-1) - pl.col("vwc").shift(1)) / 2).alias("dvwc_ctr"),
    ])
    return daily.select(["date", "vwc", "dvwc_fwd", "dvwc_ctr"])


def load_pet() -> pl.DataFrame:
    pet = pl.read_csv("plots/08_pet_daily.csv").with_columns(
        pl.col("date").str.to_date().alias("date")
    ).filter(pl.col("PET_mm_day") > 0)
    return pet


def regress(x: np.ndarray, y: np.ndarray) -> dict:
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]; y = y[mask]
    if x.size < 5:
        return {"n": int(x.size), "beta": np.nan,
                "alpha": np.nan, "r2": np.nan}
    b, a = np.polyfit(x, y, 1)
    yhat = a + b * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {"n": int(x.size), "beta": float(b), "alpha": float(a),
            "r2": (1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan}


def main() -> None:
    pet = load_pet()
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5), sharex=True)
    pet_range = np.array([0.0, float(pet["PET_mm_day"].max()) * 1.05])

    for row_i, (depth, swale_id, ctrl_id) in enumerate(PAIRS):
        for col_i, (sid, treat, color) in enumerate([
            (ctrl_id,  "control", COLOR_CTRL),
            (swale_id, "swale",   COLOR_SWALE),
        ]):
            d = load_daily_vwc(sid)
            joined = (d.join(pet, on="date", how="inner")
                       .filter((pl.col("date") >= pl.lit(DRY_START).str.to_date())
                                & (pl.col("date") <  pl.lit(DRY_END).str.to_date())
                                & (pl.col("rain_mm").is_null()
                                    | (pl.col("rain_mm") < 1.0))))

            x = joined["PET_mm_day"].to_numpy()
            y_fwd = joined["dvwc_fwd"].to_numpy() * 1000
            y_ctr = joined["dvwc_ctr"].to_numpy() * 1000
            fit_fwd = regress(x, y_fwd)
            fit_ctr = regress(x, y_ctr)

            ax = axes[row_i, col_i]
            ax.scatter(x, y_fwd, color=color, alpha=0.32, s=22,
                        edgecolor="none", label="forward Δ")
            ax.scatter(x, y_ctr, facecolor="none", edgecolor=color,
                        s=28, linewidth=0.7, label="centered Δ")
            if np.isfinite(fit_fwd["beta"]):
                ax.plot(pet_range,
                          fit_fwd["alpha"] + fit_fwd["beta"] * pet_range,
                          color="grey", linewidth=1.2, linestyle=":")
            if np.isfinite(fit_ctr["beta"]):
                ax.plot(pet_range,
                          fit_ctr["alpha"] + fit_ctr["beta"] * pet_range,
                          color="k", linewidth=1.6, linestyle="--")

            txt = (f"{display(sid)} ({treat})\n"
                    f"forward    β = {fit_fwd['beta']:+.3f},  R² = {fit_fwd['r2']:.3f}\n"
                    f"centered   β = {fit_ctr['beta']:+.3f},  R² = {fit_ctr['r2']:.3f}\n"
                    f"n_fwd = {fit_fwd['n']},  n_ctr = {fit_ctr['n']}")
            ax.text(0.03, 0.04, txt, transform=ax.transAxes,
                      fontsize=8.5, color=color, weight="bold", va="bottom",
                      bbox=dict(facecolor="white", alpha=0.92, edgecolor="none"))

            ax.axhline(0, color="grey", linewidth=0.5, linestyle=":")
            ax.set_xlim(pet_range)
            ax.set_ylabel(f"{depth} cm\nΔVWC ($10^{{-3}}$ m³/m³)")
            if row_i == 0:
                ax.set_title("Control" if treat == "control" else "Swale",
                              fontsize=11, weight="bold")
            ax.legend(loc="upper left", fontsize=8)

    for ax in axes[-1]:
        ax.set_xlabel("Hargreaves-Samani PET (mm/day)")

    fig.suptitle("Bottom slope 1 — forward vs centered first difference for ΔVWC",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
