"""Hourly PET ↔ ΔVWC regression — high-resolution transpiration test.

The daily-PET regression has a "vertical-line" artifact: daily PET is
a coarse function of T_min, T_max, and Julian day, so many days
produce identical PET values while ΔVWC on those days varies for
other reasons. Stacking those days at the same x value looks like a
column of dots.

Going to **hourly** resolution dissolves that artifact because:
  - hourly PET varies continuously through the day (half-sinusoid
    centred at solar noon, FAO-56 §3.5 / Eq. 53);
  - hourly ΔVWC also varies continuously;
  - if vegetation transpires during daylight only, the coupling
    should appear as a clean daytime drawdown at swale sensors and
    a flat night signal.

Method
------
1. Resample 5-min VWC to hourly mean per sensor (require ≥ 9 of 12
   5-min samples per hour).
2. Centered hourly first difference:
       dvwc(h) = (vwc(h+1) − vwc(h−1)) / 2
3. Disaggregate daily PM-FAO PET (or HS where PM is missing) to
   hourly using the FAO half-sinusoid:
       PET_hour(t) = (π·PET_daily / (2·N)) · sin(π·(t−t_rise)/N)
   integrating to PET_daily across daylight, 0 at night.
4. Join on (date, hour), filter to dry-season days (2024-12-01 →
   2025-04-30, rain < 1 mm), drop rows where the centered hourly
   difference is undefined.
5. Per sensor: OLS regression of hourly ΔVWC on hourly PET; report
   β, R², n. Also a composite-day plot of hourly ΔVWC stacked by
   hour-of-day to visualise the daytime drawdown signature.

Sensors compared (Bottom slope 1, both depths):
    SMS06/07 (swale)  vs  SMS15/16 (control)
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

OUT = Path("plots/07i_hourly_pet_regression.png")
DRY_START = "2024-12-01"
DRY_END   = "2025-04-30"
PHI_DEG = 1.9807

PAIRS = [
    (10, "SMS06", "SMS15"),
    (40, "SMS07", "SMS16"),
]
COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"


def solar_geometry(julian_day: int) -> tuple[float, float, float]:
    """Return (t_sunrise, t_sunset, daylength_h) in local solar time."""
    phi = math.radians(PHI_DEG)
    delta = 0.409 * math.sin(2 * math.pi * julian_day / 365 - 1.39)
    cos_ws = max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta)))
    ws = math.acos(cos_ws)
    t_set  = 12 + (12 / math.pi) * ws
    t_rise = 12 - (12 / math.pi) * ws
    return t_rise, t_set, t_set - t_rise


def hourly_pet_series(pet_daily: pl.DataFrame) -> pl.DataFrame:
    """Disaggregate daily PET to hourly via FAO half-sinusoid.

    Returns a frame with columns (date, hour, pet_h_mm_per_hour).
    """
    rows = []
    hours = np.arange(0.5, 24.5, 1.0)
    for r in pet_daily.iter_rows(named=True):
        pet = r["PET_mm_day"]
        if pet is None or pet <= 0:
            continue
        t_rise, t_set, N = solar_geometry(int(r["J"]))
        peak = (math.pi * pet) / (2 * N)
        for h in hours:
            if t_rise <= h <= t_set:
                ph = peak * math.sin(math.pi * (h - t_rise) / N)
            else:
                ph = 0.0
            rows.append((r["date"], int(h - 0.5), ph))
    return pl.DataFrame(rows, schema=["date", "hour", "pet_h"], orient="row")


def load_pet_with_J() -> pl.DataFrame:
    pm = pl.read_csv("plots/08c_pm_daily.csv").with_columns(
        pl.col("date").str.to_date().alias("date")
    )
    pm = pm.with_columns(
        pl.when(pl.col("PET_PM_mm_day").is_not_null()
                  & (pl.col("PET_PM_mm_day") > 0))
          .then(pl.col("PET_PM_mm_day"))
          .otherwise(pl.col("PET_mm_day"))
          .alias("PET_mm_day_used")
    )
    return (pm.select([pl.col("date"), pl.col("J"),
                         pl.col("PET_mm_day_used").alias("PET_mm_day"),
                         pl.col("rain_mm")]))


def hourly_vwc(sensor: str) -> pl.DataFrame:
    files = sorted(Path("cache").glob("logger=*.parquet"))
    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    df = df.filter((pl.col("sensor_id") == sensor)
                    & (pl.col("variable") == "moisture")
                    & (pl.col("value") > 0.01))
    first = df["timestamp"].min()
    df = df.filter(pl.col("timestamp") >= first + pl.duration(days=14))
    hourly = (df.with_columns([
                    pl.col("timestamp").dt.date().alias("date"),
                    pl.col("timestamp").dt.hour().alias("hour"),
                ])
                .group_by(["date", "hour"])
                .agg([pl.col("value").mean().alias("vwc"),
                      pl.col("value").count().alias("n")])
                .filter(pl.col("n") >= 9)
                .sort(["date", "hour"]))
    # centered hourly first difference
    hourly = hourly.with_columns(
        ((pl.col("vwc").shift(-1) - pl.col("vwc").shift(1)) / 2).alias("dvwc")
    )
    return hourly.select(["date", "hour", "vwc", "dvwc"])


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


def composite_dvwc_by_hour(joined: pl.DataFrame
                            ) -> tuple[np.ndarray, np.ndarray,
                                       np.ndarray, np.ndarray]:
    """Median + IQR of hourly ΔVWC per hour-of-day across the window."""
    h_arr = []
    med = []; q25 = []; q75 = []
    for h in range(24):
        v = joined.filter(pl.col("hour") == h)["dvwc"].to_numpy()
        v = v[np.isfinite(v)] * 1e6   # 10⁻⁶ m³/m³ per hour
        if v.size == 0:
            h_arr.append(h); med.append(np.nan); q25.append(np.nan); q75.append(np.nan)
            continue
        h_arr.append(h)
        med.append(float(np.median(v)))
        q25.append(float(np.quantile(v, 0.25)))
        q75.append(float(np.quantile(v, 0.75)))
    return np.array(h_arr) + 0.5, np.array(med), np.array(q25), np.array(q75)


def main() -> None:
    pet_daily = load_pet_with_J()
    pet_hourly = hourly_pet_series(
        pet_daily.filter(
            (pl.col("date") >= pl.lit(DRY_START).str.to_date())
            & (pl.col("date") <  pl.lit(DRY_END).str.to_date())
            & (pl.col("rain_mm").is_null() | (pl.col("rain_mm") < 1.0))
        )
    )

    fig, axes = plt.subplots(2, 3, figsize=(15, 9),
                              gridspec_kw=dict(width_ratios=[1.1, 1.1, 1.0]))

    for row_i, (depth, swale_id, ctrl_id) in enumerate(PAIRS):
        # Left + middle columns: regression scatter for control / swale
        for col_i, (sid, treat, color) in enumerate([
            (ctrl_id,  "control", COLOR_CTRL),
            (swale_id, "swale",   COLOR_SWALE),
        ]):
            vwc = hourly_vwc(sid)
            joined = (vwc.join(pet_hourly, on=["date", "hour"], how="inner")
                          .filter(pl.col("dvwc").is_not_null()
                                    & pl.col("pet_h").is_not_null()))
            x = joined["pet_h"].to_numpy()
            y = joined["dvwc"].to_numpy() * 1e6   # 10⁻⁶ m³/m³ per hour
            fit = regress(x, y)

            ax = axes[row_i, col_i]
            ax.scatter(x, y, color=color, alpha=0.18, s=4, edgecolor="none")
            xs = np.array([0, x.max()])
            if np.isfinite(fit["beta"]):
                ax.plot(xs, fit["alpha"] + fit["beta"] * xs,
                          color="k", linewidth=1.6, linestyle="--")
            txt = (f"{display(sid)} ({treat})\n"
                    f"β = {fit['beta']:+.2f}\n"
                    f"R² = {fit['r2']:.3f}\n"
                    f"n = {fit['n']} hours")
            ax.text(0.03, 0.96, txt, transform=ax.transAxes,
                      fontsize=9.5, color=color, weight="bold", va="top",
                      bbox=dict(facecolor="white", alpha=0.92, edgecolor="none"))
            ax.axhline(0, color="grey", linewidth=0.5, linestyle=":")
            ax.set_xlim(0, x.max() * 1.02 if x.size else 1)
            ax.set_ylabel(f"{depth} cm\nhourly ΔVWC ($10^{{-6}}$ m³/m³)")
            if row_i == 0:
                ax.set_title("Control" if treat == "control"
                                else "Swale Bot 1",
                              fontsize=11, weight="bold")
            ax.set_xlabel("Hourly PET (mm/h)")

        # Right column: composite-day ΔVWC by hour-of-day, both sensors
        ax = axes[row_i, 2]
        for sid, color, lab in [
            (ctrl_id,  COLOR_CTRL,  f"control {display(ctrl_id)}"),
            (swale_id, COLOR_SWALE, f"swale {display(swale_id)}"),
        ]:
            vwc = hourly_vwc(sid)
            joined = (vwc.join(pet_hourly, on=["date", "hour"], how="inner")
                          .filter(pl.col("dvwc").is_not_null()))
            h, med, q25, q75 = composite_dvwc_by_hour(joined)
            ax.fill_between(h, q25, q75, color=color, alpha=0.18)
            ax.plot(h, med, color=color, linewidth=2.0, marker="o",
                      markersize=3, label=lab)
        ax.axhline(0, color="grey", linewidth=0.5)
        ax.set_xlabel("Hour of day")
        ax.set_xticks(range(0, 25, 4))
        ax.set_xlim(0, 24)
        ax.set_ylabel("ΔVWC ($10^{-6}$ m³/m³ per h)")
        if row_i == 0:
            ax.set_title("Composite-day ΔVWC by hour",
                          fontsize=11, weight="bold")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)

    fig.suptitle("Hourly PET (FAO half-sine) vs centered hourly ΔVWC — "
                  "Bottom slope 1\n"
                  "Right col: composite-day stack — daytime negative "
                  "excursion = transpiration",
                  fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
