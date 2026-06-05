"""Diagnostic: do electrode / sensor surveyed elevations match the LiDAR DEM?

Two panels, canonical (180deg-rotated) frame, shared elevation colour scale:
  left  — the DEM over a wide extent, soil-profile + weather landmarks labelled.
  right — the same DEM (faded) with electrodes, soil-moisture sensors and the
          soil-profile landmarks overlaid as markers coloured by their **raw
          Z_av** on the *same* colour scale. A marker that blends into the
          background agrees with the DEM elevation; one that stands out disagrees.

No data is altered — this only visualises the surveyed Z vs the measured surface.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import Normalize

REPO = Path(__file__).resolve().parents[2]
RASTER = REPO / "plots" / "12d_dem2024_rot180_raster.xyz"
ELEC_XLSX = REPO / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
SMS_CSV = REPO / "data" / "SMS_locations.csv"
OUT = REPO / "ohmpi" / "outputs" / "diagnostics" / "dem_elevation_check.png"

CMAP = "terrain"


def rot180(x, y):
    return -np.asarray(x, float), -np.asarray(y, float)


def load_dem():
    r = np.loadtxt(RASTER)
    return r[:, 0], r[:, 1], r[:, 2]


def load_electrodes():
    m = pl.read_excel(ELEC_XLSX)
    x, y = rot180(m["X_av"].to_numpy(), m["Y_av"].to_numpy())
    return x, y, m["Z_av"].to_numpy(), m["Line"].to_list()


def load_sms():
    """Return (sensors, landmarks): each a list of (label, xrot, yrot, z)."""
    sensors, landmarks = [], []
    with SMS_CSV.open() as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            if not row or not row[0].strip():
                continue
            try:
                x = float(row[10]); y = float(row[12]); z = float(row[14])
            except (IndexError, ValueError):
                continue
            lbl = row[0].strip().strip("'\"‘’“”")
            xr, yr = rot180(x, y)
            (sensors if lbl.upper().startswith("SMS") else landmarks).append(
                (lbl, float(xr), float(yr), z)
            )
    return sensors, landmarks


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dx, dy, dz = load_dem()
    ex, ey, ez, eline = load_electrodes()
    sensors, landmarks = load_sms()

    # focus extent = instrumented area (electrodes + sensors + landmarks)
    fx = np.r_[ex, [s[1] for s in sensors], [l[1] for l in landmarks]]
    fy = np.r_[ey, [s[2] for s in sensors], [l[2] for l in landmarks]]
    x0, x1 = fx.min() - 2, fx.max() + 2
    y0, y1 = fy.min() - 2, fy.max() + 2

    # shared colour scale from the DEM **within the focus extent**, so the swale
    # elevation detail spreads across the full colormap instead of being
    # compressed by the surrounding hills.
    inbox = (dx >= x0) & (dx <= x1) & (dy >= y0) & (dy <= y1)
    vmin, vmax = np.nanpercentile(dz[inbox], [2, 98])
    norm = Normalize(vmin=vmin, vmax=vmax)              # focus scale (right panel)
    fmin, fmax = np.nanpercentile(dz, [2, 98])
    norm_full = Normalize(vmin=fmin, vmax=fmax)          # wide scale (left panel)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(20, 10))

    # ---- left: DEM wide view + landmarks ----
    sc = axL.scatter(dx, dy, c=dz, cmap=CMAP, norm=norm_full, s=4, marker="s")
    axL.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                                edgecolor="red", lw=1.5, ls="--"))
    axL.tricontour(dx, dy, dz, levels=12, colors="k", linewidths=0.3, alpha=0.4)
    for lbl, x, y, z in landmarks:
        axL.plot(x, y, "*", ms=18, mfc="magenta", mec="k", mew=1.2)
        axL.annotate(lbl, (x, y), fontsize=8, color="magenta",
                     xytext=(6, 6), textcoords="offset points")
    plt.colorbar(sc, ax=axL, label="DEM elevation [m]", shrink=0.8)
    axL.set_title("LiDAR DEM (canonical frame) + soil-profile / weather landmarks",
                  fontsize=11)
    axL.set_xlabel("x [m] (East)"); axL.set_ylabel("y [m] (North)")
    axL.set_aspect("equal"); axL.grid(alpha=0.2)

    # ---- right: DEM faded + markers coloured by raw Z_av on the SAME scale ----
    axR.scatter(dx, dy, c=dz, cmap=CMAP, norm=norm, s=4, marker="s", alpha=0.35)
    # electrodes
    axR.scatter(ex, ey, c=ez, cmap=CMAP, norm=norm, s=70, marker="o",
                edgecolor="k", linewidth=0.8, label="electrodes (raw Z_av)")
    # sms sensors
    sx = [s[1] for s in sensors]; sy = [s[2] for s in sensors]; sz = [s[3] for s in sensors]
    axR.scatter(sx, sy, c=sz, cmap=CMAP, norm=norm, s=180, marker="^",
                edgecolor="k", linewidth=1.2, label="SMS sensors (raw Z)")
    for lbl, x, y, z in sensors:
        axR.annotate(lbl.replace("SMS", ""), (x, y), fontsize=7,
                     xytext=(5, 4), textcoords="offset points")
    # soil profiles
    lx = [l[1] for l in landmarks]; ly = [l[2] for l in landmarks]; lz = [l[3] for l in landmarks]
    axR.scatter(lx, ly, c=lz, cmap=CMAP, norm=norm, s=320, marker="*",
                edgecolor="magenta", linewidth=2.0, label="soil profiles / weather (raw Z)")
    # focus extent on the instrumented area + soil profiles
    axR.set_xlim(x0, x1)
    axR.set_ylim(y0, y1)
    axR.set_title("Markers coloured by surveyed raw Z_av on the DEM colour scale\n"
                  "(marker blends in = agrees with DEM; stands out = disagrees)",
                  fontsize=11)
    axR.set_xlabel("x [m] (East)"); axR.set_ylabel("y [m] (North)")
    axR.set_aspect("equal"); axR.grid(alpha=0.2); axR.legend(loc="upper left", fontsize=9)

    fig.suptitle("Elevation cross-check: surveyed electrode/sensor Z vs LiDAR DEM "
                 "(raw Z_av, NOT negated)", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT, dpi=130, bbox_inches="tight")
    print("saved", OUT.relative_to(REPO))


if __name__ == "__main__":
    main()
