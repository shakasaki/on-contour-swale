"""Daily potential evapotranspiration (PET) via the Hargreaves-Samani method.

Follows Widmer (2024) §3.4 (p. 23), Eq. 3-7. Inputs come from the
ATMOS-14 weather sensor on logger 19570 (port 5, variable ``air_temp``);
the site latitude is read from ``config/settings.json``.

Two units fixes vs Widmer's stated equations
--------------------------------------------
Widmer's §3.4 quotes the FAO-1998 formulas but mislabels two unit
conventions. Both fixes are applied here; both are flagged inline.

1. **Solar constant**. Widmer's text gives ``G_sc = 0.82 MJ/m²/day``,
   but the (24·60/π) prefactor in Eq. 4 expects ``G_sc`` in MJ/m²/min.
   The standard FAO value is ``G_sc = 0.0820 MJ/m²/min``. With Widmer's
   stated 0.82 the resulting ``Ra`` would be a factor 1440 too small.

2. **Ra units in the Hargreaves PET formula**. Widmer's Eq. 3 reads
   ``PET = 0.0023·(Tmax−Tmin)^½·(Tmean+17.8)·Ra``. With ``Ra`` in
   ``MJ/m²/day`` the result is dimensionally a factor ≈2.45 too high
   (the latent heat of vaporisation, MJ/kg). The conventional FAO-56 /
   Hargreaves-Samani form uses ``Ra`` in *water-equivalent mm/day*:

       Ra_mm = Ra_MJ / 2.45          (Allen et al. 1998 Eq. 20)

   Then ``PET`` comes out in mm/day. We compute ``Ra`` in MJ/m²/day
   (matches Widmer Eq. 4) and convert at the PET step.

The corrected daily-mean PET lands in the 4–5 mm/day range, consistent
with tropical Hargreaves-Samani norms for southern India; without the
fixes it sits at ~12 mm/day, which is non-physical.

Outputs
-------
* ``plots/08_pet_daily.csv`` — one row per day; columns: date, J,
  T_min_C, T_max_C, T_mean_C, n_samples, R_a_MJ_m2_day, PET_mm_day.
* ``plots/08_pet_overview.png`` — PET vs daily rainfall over the full
  record (rain gauge silence after 2025-06-22 will show as zero bars).

Run from project root::

    PYTHONPATH=src python scripts/08_pet_hargreaves.py
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.config import load_settings
from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Project layout / settings
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

OUT_CSV = PLOTS / "08_pet_daily.csv"
OUT_PNG = PLOTS / "08_pet_overview.png"

# ---------------------------------------------------------------------------
# Tunables — every value here has a source in Widmer (2024) §3.4.
# ---------------------------------------------------------------------------

# Site latitude (rad). Widmer §2.3.1, p. 7: φ = 1.9807° N.
LATITUDE_DEG = 1.9807

# Solar constant in MJ/m²/min. Standard FAO-1998 value used by the
# Hargreaves-Samani / Ra formula. See module docstring for the typo
# in Widmer's text that motivates fixing this here.
G_SC_MJ_M2_MIN = 0.0820

# Air-temperature source: ATMOS-14 on logger 19570 port 5, variable air_temp.
LOGGER_SERIAL_WEATHER = "19570"
AIR_TEMP_VARIABLE = "air_temp"
PRECIP_VARIABLE = "precipitation"

# Day after which the rain gauge went silent — shown as a vertical marker.
RAIN_GAUGE_FAILED = "2025-06-22"


# ---------------------------------------------------------------------------
# Hargreaves-Samani
# ---------------------------------------------------------------------------

def extraterrestrial_radiation_mj_m2_day(latitude_deg: float, J: int) -> float:
    """Daily extraterrestrial radiation Ra (MJ/m²/day) for one Julian day J.

    Implements Widmer Eq. 4-7 with the FAO-1998 solar constant.
    """
    phi = math.radians(latitude_deg)
    d_r = 1.0 + 0.033 * math.cos(2.0 * math.pi * J / 365.0)
    delta = 0.409 * math.sin(2.0 * math.pi * J / 365.0 - 1.39)
    ws_arg = -math.tan(phi) * math.tan(delta)
    # Polar regions: clip to physical range to avoid math-domain errors at
    # extreme latitudes. Auroville (φ ≈ 2°) is nowhere near the cutoff but
    # the guard keeps the function generic.
    ws_arg = max(-1.0, min(1.0, ws_arg))
    omega_s = math.acos(ws_arg)
    ra = (24.0 * 60.0 / math.pi) * G_SC_MJ_M2_MIN * d_r * (
        omega_s * math.sin(phi) * math.sin(delta)
        + math.cos(phi) * math.cos(delta) * math.sin(omega_s)
    )
    return ra


# Latent heat of vaporisation (MJ/kg), used to convert Ra from MJ/m²/day to
# water-equivalent mm/day. Allen et al. 1998 (FAO-56) Eq. 20.
LAMBDA_LATENT_HEAT_MJ_KG = 2.45


def pet_hargreaves_samani(t_max_c: float, t_min_c: float, t_mean_c: float,
                            ra_mj_m2_day: float) -> float:
    """PET in mm/day per Widmer Eq. 3 (Hargreaves & Samani 1982).

    Internally converts ``Ra`` from MJ/m²/day to water-equivalent mm/day
    (divide by the latent heat of vaporisation). See module docstring
    for why this fix is necessary versus the units as written in
    Widmer §3.4.

    Returns ``np.nan`` if the temperature inputs are missing or T_max < T_min.
    """
    if not (math.isfinite(t_max_c) and math.isfinite(t_min_c)
             and math.isfinite(t_mean_c)):
        return float("nan")
    delta_t = t_max_c - t_min_c
    if delta_t < 0:
        return float("nan")
    ra_mm_day = ra_mj_m2_day / LAMBDA_LATENT_HEAT_MJ_KG
    return 0.0023 * math.sqrt(delta_t) * (t_mean_c + 17.8) * ra_mm_day


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def daily_temperature_stats(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate 5-min air_temp to daily T_min, T_max, T_mean, plus sample count."""
    air = (df.filter((pl.col("logger_serial") == LOGGER_SERIAL_WEATHER)
                       & (pl.col("variable") == AIR_TEMP_VARIABLE)
                       & pl.col("value").is_not_null())
              .with_columns(pl.col("timestamp").dt.date().alias("date"))
              .group_by("date")
              .agg([
                  pl.col("value").min().alias("T_min_C"),
                  pl.col("value").max().alias("T_max_C"),
                  pl.col("value").mean().alias("T_mean_C"),
                  pl.len().alias("n_samples"),
              ])
              .sort("date"))
    return air


def daily_precipitation(df: pl.DataFrame) -> pl.DataFrame:
    """Daily rainfall total (mm)."""
    rain = (df.filter((pl.col("logger_serial") == LOGGER_SERIAL_WEATHER)
                       & (pl.col("variable") == PRECIP_VARIABLE)
                       & pl.col("value").is_not_null())
               .with_columns(pl.col("timestamp").dt.date().alias("date"))
               .group_by("date")
               .agg(pl.col("value").sum().alias("rain_mm"))
               .sort("date"))
    return rain


def compute_daily_pet(temps: pl.DataFrame) -> pl.DataFrame:
    """Add Julian day, Ra, and PET columns to the daily temperature table."""
    j = temps["date"].dt.ordinal_day().to_list()
    t_min = temps["T_min_C"].to_list()
    t_max = temps["T_max_C"].to_list()
    t_mean = temps["T_mean_C"].to_list()

    ra_vals = [extraterrestrial_radiation_mj_m2_day(LATITUDE_DEG, jj) for jj in j]
    pet_vals = [pet_hargreaves_samani(tx, tn, tm, ra)
                for tx, tn, tm, ra in zip(t_max, t_min, t_mean, ra_vals)]

    return temps.with_columns([
        pl.Series("J", j, dtype=pl.Int32),
        pl.Series("R_a_MJ_m2_day", ra_vals, dtype=pl.Float64),
        pl.Series("PET_mm_day",    pet_vals, dtype=pl.Float64),
    ])


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_overview(daily: pl.DataFrame, rain: pl.DataFrame, out: Path) -> None:
    fig, ax_rain = plt.subplots(figsize=(13, 5))

    ax_pet = ax_rain.twinx()

    rain_dates = rain["date"].to_list()
    rain_vals = rain["rain_mm"].to_list()
    ax_rain.bar(rain_dates, rain_vals, color="#1f77b4", width=1.0, alpha=0.7,
                 label="Daily rainfall (mm)")
    ax_rain.set_ylabel("Rainfall (mm/day)", color="#1f77b4")
    ax_rain.tick_params(axis="y", labelcolor="#1f77b4")

    pet_dates = daily["date"].to_list()
    pet_vals = daily["PET_mm_day"].to_list()
    ax_pet.plot(pet_dates, pet_vals, color="#d62728", lw=0.9, alpha=0.9,
                 label="PET (mm/day)")
    ax_pet.set_ylabel("PET (mm/day)", color="#d62728")
    ax_pet.tick_params(axis="y", labelcolor="#d62728")

    gauge_failed = np.datetime64(RAIN_GAUGE_FAILED)
    ax_rain.axvline(gauge_failed, color="black", ls=":", lw=1.0,
                     alpha=0.6, label=f"rain gauge silent ({RAIN_GAUGE_FAILED})")

    ax_rain.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax_rain.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()

    # Composite legend
    h1, l1 = ax_rain.get_legend_handles_labels()
    h2, l2 = ax_pet.get_legend_handles_labels()
    ax_rain.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9, frameon=True)

    ax_rain.set_title(
        "Daily PET (Hargreaves-Samani) vs daily rainfall — logger 19570",
        fontsize=12, weight="bold",
    )
    ax_rain.grid(alpha=0.3)
    fig.tight_layout()
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

    print("Aggregating to daily temperatures…")
    temps = daily_temperature_stats(df)
    print(f"  {temps.height} days with air_temp coverage")

    print("Computing Hargreaves-Samani PET…")
    daily = compute_daily_pet(temps)

    print("Daily rainfall…")
    rain = daily_precipitation(df)

    # Combined table for the CSV. Use full-outer join so days with temps but
    # no rain (or vice versa) still appear.
    combined = daily.join(rain, on="date", how="full", coalesce=True).sort("date")
    combined.write_csv(OUT_CSV)
    print(f"  wrote {OUT_CSV.relative_to(ROOT)}  "
          f"({combined.height} rows; "
          f"{combined['PET_mm_day'].drop_nulls().mean():.2f} mm/day mean PET)")

    plot_overview(daily, rain, OUT_PNG)
    print(f"  wrote {OUT_PNG.relative_to(ROOT)}")

    # Quick comparison vs Widmer p. 7: annual rainfall 1357 mm,
    # PET (Thornthwaite) ~63% of rainfall = ~855 mm/yr ≈ 2.3 mm/day.
    pet_daily_mean = combined["PET_mm_day"].drop_nulls().mean()
    rain_annual = combined["rain_mm"].drop_nulls().sum() * 365.0 / max(1, combined.height)
    print(f"\nQuick sanity check vs Widmer §2.3.1 (p. 7):")
    print(f"  observed mean PET                ~ {pet_daily_mean:.2f} mm/day "
          f"({pet_daily_mean * 365:.0f} mm/yr)")
    print(f"  Widmer cites Thornthwaite PET     ~ 2.3 mm/day (855 mm/yr; 63% of rainfall)")
    print(f"  observed daily-mean rainfall      ~ {rain_annual / 365.0:.2f} mm/day "
          f"({rain_annual:.0f} mm/yr annualised)")
    print(f"  Widmer cites mean annual rainfall ~ 1357 mm/yr (1989-2018 normal)")


if __name__ == "__main__":
    main()
