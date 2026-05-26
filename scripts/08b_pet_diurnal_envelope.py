"""Visualise the PET we compute.

Three panels:
  (a) daily PET over the full record (with dry-season window shaded)
  (b) a representative week of hourly PET, disaggregated from daily
      totals via a half-sinusoid centred at solar noon (FAO-56 §3.5).
      Sunrise/sunset are computed from latitude + Julian day, so the
      length and centring of the daylight half-sine track the sun
      cycle.
  (c) composite-day plot — every day of the dry-season record stacked
      by hour-of-day, showing median + IQR + min/max envelope. This
      is the "shape of a typical day" of PET.

Hourly disaggregation
---------------------
For each day:

    ω_s   = arccos(-tan(φ)·tan(δ))          # sunset hour angle
    t_set = 12 + (12/π)·ω_s                  # local solar time
    t_rise = 12 - (12/π)·ω_s
    N      = t_set - t_rise                  # daylength (hours)

    PET_hour(t) = (π·PET_daily / (2·N)) · sin(π·(t − t_rise)/N)
                  for t in [t_rise, t_set];  0 otherwise

This satisfies ∫₀²⁴ PET_hour(t) dt = PET_daily exactly.

Auroville is at φ = 1.9807°N → daylength is ~12.0–12.2 h year-round
with tiny seasonal variation, so the "daytime envelope" is very
stable.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

PHI_DEG = 1.9807
OUT = Path("plots/08b_pet_diurnal_envelope.png")

# Representative dry-season week to show hourly disaggregation.
WEEK_START = "2025-02-10"
WEEK_END   = "2025-02-17"

DRY_START = "2024-12-01"
DRY_END   = "2025-04-30"


def solar_geometry(julian_day: int, phi_rad: float
                    ) -> tuple[float, float, float]:
    """Return (t_sunrise, t_sunset, daylength_h) in local solar time."""
    delta = 0.409 * math.sin(2 * math.pi * julian_day / 365 - 1.39)
    cos_ws = -math.tan(phi_rad) * math.tan(delta)
    cos_ws = max(-1.0, min(1.0, cos_ws))
    ws = math.acos(cos_ws)
    t_set  = 12 + (12 / math.pi) * ws
    t_rise = 12 - (12 / math.pi) * ws
    return t_rise, t_set, t_set - t_rise


def hourly_pet_for_day(pet_daily: float, julian_day: int,
                        hours: np.ndarray) -> np.ndarray:
    phi = math.radians(PHI_DEG)
    t_rise, t_set, N = solar_geometry(julian_day, phi)
    out = np.zeros_like(hours, dtype=float)
    day_mask = (hours >= t_rise) & (hours <= t_set)
    out[day_mask] = (math.pi * pet_daily / (2 * N)) * np.sin(
        math.pi * (hours[day_mask] - t_rise) / N
    )
    return out


def build_hourly_matrix(pet_daily: pl.DataFrame
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Return (hours_24, hourly_matrix) where each row is one day."""
    hours = np.arange(0.5, 24.5, 1.0)  # midpoint of each hourly bin
    rows = []
    for pet, j in zip(pet_daily["PET_mm_day"].to_numpy(),
                        pet_daily["J"].to_numpy()):
        if pet <= 0 or not np.isfinite(pet):
            continue
        rows.append(hourly_pet_for_day(float(pet), int(j), hours))
    return hours, np.vstack(rows)


def main() -> None:
    pet = pl.read_csv("plots/08_pet_daily.csv").with_columns(
        pl.col("date").str.to_date().alias("date")
    ).filter(pl.col("PET_mm_day") > 0)

    fig = plt.figure(figsize=(12, 9))
    gs = fig.add_gridspec(3, 1, height_ratios=[1, 1, 1.05], hspace=0.40)
    ax_a = fig.add_subplot(gs[0])
    ax_b = fig.add_subplot(gs[1])
    ax_c = fig.add_subplot(gs[2])

    # ---- (a) daily PET over full record ----
    dates = pet["date"].to_numpy()
    pet_d = pet["PET_mm_day"].to_numpy()
    ax_a.plot(dates, pet_d, color="#1f3a5f", linewidth=0.8)
    ax_a.fill_between(dates, 0, pet_d, color="#1f3a5f", alpha=0.18)
    # shade the dry-season window
    ax_a.axvspan(np.datetime64(DRY_START), np.datetime64(DRY_END),
                  color="#d62728", alpha=0.10,
                  label=f"dry season ({DRY_START} → {DRY_END})")
    ax_a.set_ylabel("Daily PET (mm/day)")
    ax_a.set_title("(a) Daily Hargreaves-Samani PET, full record",
                    fontsize=11, weight="bold")
    ax_a.axhline(float(pet_d.mean()), color="k", linestyle="--", linewidth=0.8,
                  label=f"mean = {pet_d.mean():.2f} mm/day")
    ax_a.legend(loc="upper right", fontsize=8)
    ax_a.grid(alpha=0.3)

    # ---- (b) representative dry-season week, hourly disaggregation ----
    week = pet.filter((pl.col("date") >= pl.lit(WEEK_START).str.to_date())
                       & (pl.col("date") <= pl.lit(WEEK_END).str.to_date()))
    hours = np.arange(0.5, 24.5, 1.0)
    for i, (d, p, j) in enumerate(zip(week["date"].to_numpy(),
                                         week["PET_mm_day"].to_numpy(),
                                         week["J"].to_numpy())):
        hourly = hourly_pet_for_day(float(p), int(j), hours)
        # x in hours since first day of the week
        x_h = hours + i * 24
        ax_b.plot(x_h, hourly, color="#1f3a5f", linewidth=1.2)
        ax_b.fill_between(x_h, 0, hourly, color="#f1c232", alpha=0.45)
    # day boundaries + labels
    for i, d in enumerate(week["date"].to_numpy()):
        if i > 0:
            ax_b.axvline(i * 24, color="grey", linewidth=0.4, linestyle=":")
        ax_b.text(i * 24 + 12, ax_b.get_ylim()[1] * 0.92 if i > 0 else 0.4,
                   str(d)[5:], ha="center", fontsize=7, color="dimgrey")
    ax_b.set_ylabel("Hourly PET (mm/h)")
    ax_b.set_xlabel("Hours since start of week")
    ax_b.set_title(f"(b) Representative week {WEEK_START} → {WEEK_END} — "
                    "hourly PET, half-sinusoid disaggregation",
                    fontsize=11, weight="bold")
    ax_b.grid(alpha=0.3)
    ax_b.set_xlim(0, len(week) * 24)

    # ---- (c) composite-day envelope across the dry-season record ----
    pet_dry = pet.filter((pl.col("date") >= pl.lit(DRY_START).str.to_date())
                          & (pl.col("date") <  pl.lit(DRY_END).str.to_date()))
    hours_c, H = build_hourly_matrix(pet_dry)
    median = np.median(H, axis=0)
    q25 = np.quantile(H, 0.25, axis=0)
    q75 = np.quantile(H, 0.75, axis=0)
    pmin = np.min(H, axis=0)
    pmax = np.max(H, axis=0)
    ax_c.fill_between(hours_c, pmin, pmax, color="#f1c232", alpha=0.25,
                       label="min–max envelope")
    ax_c.fill_between(hours_c, q25, q75, color="#f1c232", alpha=0.55,
                       label="IQR (25–75 %)")
    ax_c.plot(hours_c, median, color="#1f3a5f", linewidth=2.0,
               marker="o", markersize=4, label="median")
    ax_c.set_ylabel("Hourly PET (mm/h)")
    ax_c.set_xlabel("Hour of day (local solar time)")
    ax_c.set_xticks(range(0, 25, 3))
    ax_c.set_xlim(0, 24)
    ax_c.set_title(f"(c) Composite-day PET envelope across the dry season "
                    f"(N = {H.shape[0]} days)",
                    fontsize=11, weight="bold")
    ax_c.legend(loc="upper right", fontsize=8)
    ax_c.grid(alpha=0.3)

    fig.suptitle("Hargreaves-Samani PET — daily series, hourly "
                  "disaggregation, composite-day envelope",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
