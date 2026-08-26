"""Penman-Monteith FAO-56 PET — energy-balance reference compared to
Hargreaves-Samani.

Implements the FAO-56 reference ETo (Allen et al. 1998, Eq. 6) with
"reduced-data" assumptions where on-site measurements are missing:

    ETo = (0.408·Δ·(Rn − G) + γ·(900/(T+273))·u₂·(es − ea))
           ───────────────────────────────────────────────────
                          Δ + γ·(1 + 0.34·u₂)

Variables and sources
---------------------
| Symbol | Quantity                       | Source                          |
| ------ | ------------------------------ | ------------------------------- |
| T_max  | daily max air temperature      | ATMOS-14 air_temp (measured)    |
| T_min  | daily min air temperature      | ATMOS-14 air_temp (measured)    |
| T_mean | (T_max + T_min) / 2            | derived                         |
| P      | atmospheric pressure           | ATMOS-14 atm_pressure (measured)|
| ea     | actual vapour pressure         | ATMOS-14 vapor_pressure (measured, starts 2024-07-23) |
| u₂     | wind speed at 2 m              | **assumed 2 m/s** (FAO default — no anemometer) |
| Ra     | extraterrestrial radiation     | computed from latitude + Julian day |
| Rs     | solar radiation                | **estimated** Rs = K_rs·√(T_max−T_min)·Ra (FAO Eq. 50, no pyranometer) |
| Rn     | net radiation                  | derived from Rs (FAO Eqs. 37–40) |
| G      | soil heat flux                 | ≈ 0 for daily                    |

K_rs = 0.19 (coastal value — Auroville is ~10 km from the Bay of
Bengal); FAO recommends 0.16 for interior locations. We use 0.19.

Constants:
    σ        = 4.903e-9 MJ/K⁴·m²·day   (Stefan-Boltzmann, daily)
    α        = 0.23                    (albedo of reference grass)
    elevation z ≈ 30 m (Auroville plateau)
    Rso      = (0.75 + 2e-5·z)·Ra      (clear-sky solar radiation)

Outputs
-------
    plots/08c_pm_daily.csv        — one row per day, PM-FAO inputs +
                                    output PET_PM_mm_day.
    plots/08c_hs_vs_pm.png        — comparison HS vs PM (time series,
                                    scatter, monthly ratio).

References
----------
Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998).
"Crop evapotranspiration — Guidelines for computing crop water
requirements." FAO Irrigation and Drainage Paper 56, Rome.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

OUT_CSV = Path("plots/08c_pm_daily.csv")
OUT_PNG = Path("plots/08c_hs_vs_pm.png")

PHI_DEG = 1.9807         # site latitude, °N
ELEV_M  = 30.0           # Auroville plateau elevation, m
K_RS    = 0.19           # coastal Hargreaves coefficient (FAO §3.5.4)
ALBEDO  = 0.23           # reference grass surface
SIGMA   = 4.903e-9       # MJ/K⁴·m²·day  (Stefan-Boltzmann, daily)
U2_DEFAULT = 2.0         # m/s, FAO default when wind is missing


def es_kpa(T_C: float) -> float:
    """Saturation vapour pressure (kPa) at temperature T (°C) — FAO Eq. 11."""
    return 0.6108 * math.exp(17.27 * T_C / (T_C + 237.3))


def slope_es(T_C: float) -> float:
    """Slope of saturation vapour pressure curve Δ (kPa/°C) — FAO Eq. 13."""
    return 4098.0 * es_kpa(T_C) / (T_C + 237.3) ** 2


def gamma_psych(P_kpa: float) -> float:
    """Psychrometric constant γ (kPa/°C) — FAO Eq. 8."""
    return 0.000665 * P_kpa


def net_radiation(Tmax_C: float, Tmin_C: float, Ra: float, Rs: float,
                   ea_kpa: float) -> float:
    """Daily net radiation Rn (MJ/m²/day) — FAO Eqs. 37–40."""
    Rso = (0.75 + 2.0e-5 * ELEV_M) * Ra          # Eq. 37
    Rns = (1.0 - ALBEDO) * Rs                    # Eq. 38
    Tmax_K = Tmax_C + 273.16
    Tmin_K = Tmin_C + 273.16
    # Eq. 39 — clip Rs/Rso to [0.33, 1.0] per FAO recommendation
    rs_over_rso = max(0.33, min(1.0, Rs / Rso if Rso > 0 else 0.0))
    Rnl = (SIGMA * ((Tmax_K**4 + Tmin_K**4) / 2.0)
            * (0.34 - 0.14 * math.sqrt(max(ea_kpa, 0.0)))
            * (1.35 * rs_over_rso - 0.35))           # Eq. 39
    return Rns - Rnl                                # Eq. 40


def pm_fao_eto(Tmax_C: float, Tmin_C: float, P_kpa: float,
                ea_kpa: float, Ra: float,
                u2: float = U2_DEFAULT) -> dict:
    """Daily Penman-Monteith reference ETo (mm/day) and the diagnostics."""
    if not all(np.isfinite([Tmax_C, Tmin_C, P_kpa, ea_kpa, Ra])):
        return {k: np.nan for k in ("ETo", "Rs", "Rn", "es", "VPD",
                                       "delta", "gamma")}
    if Tmax_C < Tmin_C:
        return {k: np.nan for k in ("ETo", "Rs", "Rn", "es", "VPD",
                                       "delta", "gamma")}
    T_mean = 0.5 * (Tmax_C + Tmin_C)
    Rs = K_RS * math.sqrt(Tmax_C - Tmin_C) * Ra         # FAO Eq. 50
    es = 0.5 * (es_kpa(Tmax_C) + es_kpa(Tmin_C))        # FAO Eq. 12
    VPD = max(es - ea_kpa, 0.0)
    delta = slope_es(T_mean)                             # FAO Eq. 13
    gamma = gamma_psych(P_kpa)                           # FAO Eq. 8
    Rn = net_radiation(Tmax_C, Tmin_C, Ra, Rs, ea_kpa)

    numerator = (0.408 * delta * Rn
                  + gamma * (900.0 / (T_mean + 273.0)) * u2 * VPD)
    denominator = delta + gamma * (1.0 + 0.34 * u2)
    eto = numerator / denominator if denominator > 0 else np.nan
    return {"ETo": eto, "Rs": Rs, "Rn": Rn, "es": es, "VPD": VPD,
            "delta": delta, "gamma": gamma}


def build_daily_meteo() -> pl.DataFrame:
    """Aggregate ATMOS-14 5-min readings to daily min/max/mean."""
    df = pl.read_parquet("cache/logger=19570.parquet")
    atmos = df.filter(pl.col("sensor_type") == "ATMOS14")
    # Wide pivot of the variables we need
    wanted = ["air_temp", "atm_pressure", "vapor_pressure"]
    sub = atmos.filter(pl.col("variable").is_in(wanted))
    sub = sub.with_columns(pl.col("timestamp").dt.date().alias("date"))
    daily = (sub.group_by(["date", "variable"])
                 .agg([pl.col("value").mean().alias("mean"),
                       pl.col("value").min().alias("min"),
                       pl.col("value").max().alias("max"),
                       pl.col("value").count().alias("n")]))
    # Wide
    out = (daily.filter(pl.col("variable") == "air_temp")
                  .select([pl.col("date"),
                           pl.col("min").alias("T_min"),
                           pl.col("max").alias("T_max"),
                           pl.col("mean").alias("T_mean"),
                           pl.col("n").alias("n_T")]))
    out = out.join(
        daily.filter(pl.col("variable") == "atm_pressure")
              .select([pl.col("date"), pl.col("mean").alias("P_kpa")]),
        on="date", how="left",
    )
    out = out.join(
        daily.filter(pl.col("variable") == "vapor_pressure")
              .select([pl.col("date"), pl.col("mean").alias("ea_kpa")]),
        on="date", how="left",
    )
    return out.sort("date").filter(pl.col("n_T") >= 200)


def main() -> None:
    hs = pl.read_csv("plots/08_pet_daily.csv").with_columns(
        pl.col("date").str.to_date().alias("date")
    )
    meteo = build_daily_meteo()
    joined = meteo.join(
        hs.select(["date", "J", "R_a_MJ_m2_day", "PET_mm_day", "rain_mm"]),
        on="date", how="inner",
    )

    pm_rows = []
    for r in joined.iter_rows(named=True):
        if (r["T_min"] is None or r["T_max"] is None
                or r["P_kpa"] is None or r["ea_kpa"] is None
                or r["R_a_MJ_m2_day"] is None):
            res = {k: np.nan for k in ("ETo", "Rs", "Rn", "es", "VPD",
                                          "delta", "gamma")}
        else:
            res = pm_fao_eto(r["T_max"], r["T_min"], r["P_kpa"],
                              r["ea_kpa"], r["R_a_MJ_m2_day"])
        pm_rows.append(res["ETo"])
    joined = joined.with_columns(pl.Series("PET_PM_mm_day", pm_rows))

    out = joined.select(["date", "J", "T_min", "T_max", "T_mean",
                          "P_kpa", "ea_kpa", "R_a_MJ_m2_day",
                          "PET_mm_day", "PET_PM_mm_day", "rain_mm"])
    out.write_csv(OUT_CSV)
    print(f"wrote {OUT_CSV}  rows={out.height}")

    # ---- figure: HS vs PM ----
    valid = out.filter(pl.col("PET_PM_mm_day").is_not_null()
                        & pl.col("PET_mm_day").is_not_null()
                        & (pl.col("PET_mm_day") > 0)
                        & (pl.col("PET_PM_mm_day") > 0))
    dates = valid["date"].to_numpy()
    hs_v  = valid["PET_mm_day"].to_numpy()
    pm_v  = valid["PET_PM_mm_day"].to_numpy()

    fig, axes = plt.subplots(2, 2, figsize=(12, 8),
                              gridspec_kw=dict(height_ratios=[1, 1]))

    # (a) time series
    ax = axes[0, 0]
    ax.plot(dates, hs_v, color="#1f3a5f", linewidth=0.8, label="Hargreaves-Samani")
    ax.plot(dates, pm_v, color="#d62728", linewidth=0.8, label="Penman-Monteith FAO-56")
    ax.set_ylabel("Daily PET (mm/day)")
    ax.set_title("(a) HS vs PM daily PET, full overlapping record",
                  fontsize=11, weight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    # (b) scatter with 1:1 line
    ax = axes[0, 1]
    ax.scatter(hs_v, pm_v, color="#1f77b4", s=10, alpha=0.5, edgecolor="none")
    lim = [0, max(hs_v.max(), pm_v.max()) * 1.05]
    ax.plot(lim, lim, color="k", linestyle="--", linewidth=1.0,
              label="1:1 line")
    # OLS through origin slope
    b = float(np.sum(hs_v * pm_v) / np.sum(hs_v * hs_v))
    ax.plot(lim, [b * l for l in lim], color="r", linewidth=1.4,
              label=f"PM = {b:.2f} · HS")
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Hargreaves-Samani PET (mm/day)")
    ax.set_ylabel("Penman-Monteith PET (mm/day)")
    ax.set_title(f"(b) Scatter (n = {len(hs_v)} days)", fontsize=11, weight="bold")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)

    # (c) ratio PM/HS over time
    ax = axes[1, 0]
    ratio = pm_v / hs_v
    ax.plot(dates, ratio, color="#444", linewidth=0.6, alpha=0.7)
    ax.axhline(np.median(ratio), color="r", linestyle="--",
                label=f"median ratio = {np.median(ratio):.2f}")
    ax.set_ylabel("PM / HS ratio")
    ax.set_title("(c) Daily PM / HS ratio — < 1 means HS over-predicts",
                  fontsize=11, weight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)

    # (d) annual + monsoon-vs-dry stats
    ax = axes[1, 1]
    ax.axis("off")
    stats_txt = (
        f"Means over n = {len(hs_v)} days\n"
        f"  HS:  {hs_v.mean():.2f}  mm/day  →  {hs_v.mean()*365:.0f} mm/yr\n"
        f"  PM:  {pm_v.mean():.2f}  mm/day  →  {pm_v.mean()*365:.0f} mm/yr\n"
        f"\n"
        f"Median ratio PM / HS = {np.median(ratio):.3f}\n"
        f"  → HS over-predicts by ~{(1/np.median(ratio) - 1)*100:.0f} %\n"
        f"\n"
        f"Widmer (2024) Thornthwaite estimate ≈ 2.3 mm/day (855 mm/yr)\n"
        f"PM here lands {'above' if pm_v.mean() > 2.3 else 'below'} her Thornthwaite.\n"
        f"\n"
        f"Inputs status:\n"
        f"  T_max, T_min       — measured (ATMOS-14)\n"
        f"  P (kPa)            — measured (ATMOS-14)\n"
        f"  ea (kPa)           — measured (ATMOS-14, since 2024-07-23)\n"
        f"  u₂ (m/s)           — assumed 2 m/s (FAO default)\n"
        f"  Rs (MJ/m²/day)     — estimated K_rs·√ΔT·R_a  (no pyranometer)\n"
        f"  Rn                 — derived from Rs (FAO §3.6)\n"
        f"  G                  — ≈ 0 for daily\n"
    )
    ax.text(0.0, 1.0, stats_txt, transform=ax.transAxes,
              fontsize=9.5, family="monospace", va="top")

    fig.suptitle("Penman-Monteith FAO-56 vs Hargreaves-Samani PET",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT_PNG, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
