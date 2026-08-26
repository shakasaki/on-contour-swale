"""PET vs ΔVWC regression — test for transpiration signature.

For two slope positions (Mid/Mound and Bottom 1) and two depths
(10 cm + 40 cm), regress daily dry-season ΔVWC against **Penman-
Monteith FAO-56** PET (Allen et al. 1998, Eq. 6 — see
`scripts/08c_penman_monteith.py` for the implementation and
`notes/processing_steps.md` §E for the measured-vs-assumed input
table).  Hargreaves-Samani is kept as a fallback when the PM-input
data is missing.

Two smoothing variants per panel: raw daily and 7-day centered
rolling mean.  Steeper negative slope = more PET-driven water loss
= transpiration signature.

ΔVWC uses a **centered first difference** (2nd-order accurate):

    dvwc(d) = (vwc(d+1) − vwc(d−1)) / 2

Forward difference (1st-order) gave the same conclusions but is
marginally noisier; see `07h_centered_vs_forward.png` for the
side-by-side check.

Sensors compared:
    Mid / Mound:   SMS04/05 (swale Mound)  vs  SMS13/14 (control Mid)
    Bottom slope:  SMS06/07 (swale Bot 1)  vs  SMS15/16 (control Bot)

Window: 2024-12-01 → 2025-04-30 (rain gauge healthy, zero rain).
Drops PET = 0 days (bad T_min/T_max readings) and days with > 1 mm
of rain.

Output:
    plots/07g_pet_vs_dvwc_mid_mound.png
    plots/07g_pet_vs_dvwc_bottom.png

Each figure: 2 rows (depth) × 2 cols (control / swale). Scatter shows
the 7-day-smoothed series; fit lines for both daily and 7-day series
overlaid (dotted = daily, dashed = 7-day). Annotated β for both.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

DRY_START = "2024-12-01"
DRY_END   = "2025-04-30"
SMOOTH_WINDOW_DAYS = 7

COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"

GROUPS = {
    "mid_mound": {
        "title": "Mid / Mound",
        "pairs": [
            (10, "SMS04", "SMS13"),
            (40, "SMS05", "SMS14"),
        ],
        "labels": ("swale Mound (SMS04/05)", "control Mid (SMS13/14)"),
    },
    "bottom": {
        "title": "Bottom slope",
        "pairs": [
            (10, "SMS06", "SMS15"),
            (40, "SMS07", "SMS16"),
        ],
        "labels": ("swale Bot 1 (SMS06/07)", "control Bot (SMS15/16)"),
    },
}


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
    # Centered first difference (2nd-order accurate)
    daily = daily.with_columns(
        ((pl.col("vwc").shift(-1) - pl.col("vwc").shift(1)) / 2).alias("dvwc")
    )
    return daily.select(["date", "vwc", "dvwc"])


def load_pet() -> pl.DataFrame:
    """Load PM-FAO PET (preferred) joined with rain_mm.

    Returns a frame with a single `PET_mm_day` column (PM-FAO values)
    and `rain_mm` from the original HS source for the rain-filter step.
    Falls back to HS where PM is unavailable (very early record before
    the ATMOS-14 vapor-pressure channel was logging).
    """
    pet = pl.read_csv("plots/08c_pm_daily.csv").with_columns(
        pl.col("date").str.to_date().alias("date")
    )
    pet = pet.with_columns(
        pl.when(pl.col("PET_PM_mm_day").is_not_null()
                  & (pl.col("PET_PM_mm_day") > 0))
          .then(pl.col("PET_PM_mm_day"))
          .otherwise(pl.col("PET_mm_day"))
          .alias("PET_mm_day_used")
    )
    return (pet.filter(pl.col("PET_mm_day_used") > 0)
                .select([pl.col("date"),
                          pl.col("PET_mm_day_used").alias("PET_mm_day"),
                          pl.col("rain_mm")]))


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
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"n": int(x.size), "beta": float(b),
            "alpha": float(a), "r2": r2}


def panel(ax, joined: pl.DataFrame, sid: str, treat: str,
            depth: int, color: str, pet_range: np.ndarray) -> None:
    pet_daily  = joined["PET_mm_day"].to_numpy()
    dvwc_daily = joined["dvwc"].to_numpy() * 1000  # 10⁻³ m³/m³

    # 7-day centered rolling mean on both series
    pet_smooth  = (joined.with_columns(
                        pl.col("PET_mm_day").rolling_mean(SMOOTH_WINDOW_DAYS,
                                                            center=True).alias("p"))
                          ["p"].to_numpy())
    dvwc_smooth = (joined.with_columns(
                        pl.col("dvwc").rolling_mean(SMOOTH_WINDOW_DAYS,
                                                      center=True).alias("d"))
                          ["d"].to_numpy()) * 1000

    fit_d  = regress(pet_daily, dvwc_daily)
    fit_7d = regress(pet_smooth, dvwc_smooth)

    ax.scatter(pet_daily, dvwc_daily, color=color, alpha=0.25,
                s=14, edgecolor="none", label="daily")
    ax.scatter(pet_smooth, dvwc_smooth, color=color, alpha=0.85,
                s=28, edgecolor="white", linewidth=0.4, label="7-d smoothed")
    if np.isfinite(fit_d["beta"]):
        ax.plot(pet_range, fit_d["alpha"] + fit_d["beta"] * pet_range,
                  color="grey", linewidth=1.2, linestyle=":")
    if np.isfinite(fit_7d["beta"]):
        ax.plot(pet_range, fit_7d["alpha"] + fit_7d["beta"] * pet_range,
                  color="k", linewidth=1.8, linestyle="--")

    txt = (f"{display(sid)} ({treat})\n"
            f"daily   β = {fit_d['beta']:+.3f}, R² = {fit_d['r2']:.3f}\n"
            f"7-d     β = {fit_7d['beta']:+.3f}, R² = {fit_7d['r2']:.3f}\n"
            f"n = {fit_d['n']} days")
    ax.text(0.03, 0.04, txt, transform=ax.transAxes,
              fontsize=8.5, color=color, weight="bold",
              va="bottom",
              bbox=dict(facecolor="white", alpha=0.92, edgecolor="none"))
    ax.axhline(0, color="grey", linewidth=0.6, linestyle=":")
    ax.set_xlim(pet_range)
    ax.set_ylabel(f"{depth} cm\nΔVWC ($10^{{-3}}$ m³/m³ over 1 day)")


def make_figure(group_key: str, daily: dict[str, pl.DataFrame],
                 pet: pl.DataFrame) -> Path:
    spec = GROUPS[group_key]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5), sharex=True)
    pet_range = np.array([0.0, float(pet["PET_mm_day"].max()) * 1.05])

    for row_i, (depth, swale_id, ctrl_id) in enumerate(spec["pairs"]):
        for col_i, (sid, treat, color) in enumerate([
            (ctrl_id,  "control", COLOR_CTRL),
            (swale_id, "swale",   COLOR_SWALE),
        ]):
            d = daily[sid]
            joined = (d.join(pet, on="date", how="inner")
                       .filter((pl.col("date") >= pl.lit(DRY_START).str.to_date())
                                & (pl.col("date") <  pl.lit(DRY_END).str.to_date())
                                & (pl.col("rain_mm").is_null()
                                    | (pl.col("rain_mm") < 1.0))
                                & pl.col("dvwc").is_not_null()))
            panel(axes[row_i, col_i], joined, sid, treat, depth, color, pet_range)
            if row_i == 0:
                axes[row_i, col_i].set_title(
                    "Control" if treat == "control" else "Swale",
                    fontsize=11, weight="bold")

    for ax in axes[-1]:
        ax.set_xlabel("Hargreaves-Samani PET (mm/day)")

    fig.suptitle(f"{spec['title']} — Penman-Monteith PET vs centered "
                  f"ΔVWC, dry season 2024-12 → 2025-04\n"
                  "Steeper negative slope = more PET-driven loss "
                  "= transpiration signature",
                  fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = Path(f"plots/07g_pet_vs_dvwc_{group_key}.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def main() -> None:
    pet = load_pet()
    sensors = {sid for g in GROUPS.values()
                    for _, sw, ct in g["pairs"]
                    for sid in (sw, ct)}
    daily = {sid: load_daily_vwc(sid) for sid in sensors}
    for key in GROUPS:
        out = make_figure(key, daily, pet)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
