"""Electrode layout figure: plan view over the DEM hillshade + an elevation panel.

Electrode positions (merged_electrode_table.xlsx) and the DEM
(data/DEM/DEM_2024_07_25.txt) share the same relative survey frame — the
electrodes fall inside the DEM cloud and their Z ranges agree — so they overlay
directly with no registration step.

Left  : plan view. DEM hillshade at 0.5 opacity behind; electrodes coloured by
        line and labelled by survey electrode number (1–50). OhmPi channel (the
        number used in the quad a/b/m/n) is in merged_electrode_table.xlsx.
Right : elevation — electrode height Z vs distance along each line, same colours.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import LightSource
from scipy.interpolate import griddata

REPO = Path(__file__).resolve().parents[2]
GEOM = REPO / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
DEM = REPO / "data" / "DEM" / "DEM_2024_07_25.txt"
OUT = REPO / "ohmpi" / "plots" / "geometry"
OUT.mkdir(parents=True, exist_ok=True)

LINE_COLORS = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green",
               "D": "tab:red", "E": "tab:purple"}
MARGIN = 2.0  # m of DEM context around the electrode bounding box


def dem_hillshade(xlim, ylim, n=400):
    """Grid the DEM over [xlim,ylim] and return an RGB hillshade for imshow."""
    d = np.loadtxt(DEM, usecols=(0, 1, 2))
    gx = np.linspace(*xlim, n)
    gy = np.linspace(*ylim, n)
    GX, GY = np.meshgrid(gx, gy)
    GZ = griddata(d[:, :2], d[:, 2], (GX, GY), method="linear")
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(np.ma.masked_invalid(GZ), cmap=plt.cm.gray,
                   vert_exag=3, blend_mode="soft")
    return rgb, GZ


def main() -> None:
    m = pl.read_excel(GEOM)
    x = m["X_av"].to_numpy()
    y = m["Y_av"].to_numpy()
    xlim = (x.min() - MARGIN, x.max() + MARGIN)
    ylim = (y.min() - MARGIN, y.max() + MARGIN)

    fig, (axp, axe) = plt.subplots(1, 2, figsize=(16, 7),
                                   gridspec_kw={"width_ratios": [1.4, 1]})

    # --- plan view over DEM hillshade ---
    rgb, _ = dem_hillshade(xlim, ylim)
    axp.imshow(rgb, extent=[*xlim, *ylim], origin="lower", alpha=0.5, zorder=1)
    for line, c in LINE_COLORS.items():
        d = m.filter(pl.col("Line") == line).sort("Electrode number for survey")
        axp.plot(d["X_av"], d["Y_av"], "-", color=c, lw=1.2, alpha=0.7,
                 zorder=2, label=f"line {line}")
        axp.scatter(d["X_av"], d["Y_av"], s=90, color=c, edgecolor="k",
                    zorder=3)
    for ch_surv, xx, yy in m.select(
        "Electrode number for survey", "X_av", "Y_av"
    ).iter_rows():
        axp.annotate(str(ch_surv), (xx, yy), fontsize=6, ha="center",
                     va="center", zorder=4, color="white", weight="bold")
    axp.set_xlim(xlim); axp.set_ylim(ylim); axp.set_aspect("equal")
    axp.set_xlabel("X [m]"); axp.set_ylabel("Y [m]")
    axp.legend(loc="upper right", fontsize=9)
    axp.set_title("Electrode layout over DEM hillshade (survey electrode no.)")

    # --- elevation panel: Z along each line ---
    for line, c in LINE_COLORS.items():
        d = m.filter(pl.col("Line") == line).sort("Electrode number for survey")
        xyz = d.select("X_av", "Y_av", "Z_av").to_numpy()
        dist = np.concatenate([[0], np.cumsum(
            np.linalg.norm(np.diff(xyz[:, :2], axis=0), axis=1))])
        axe.plot(dist, xyz[:, 2], "o-", color=c, ms=5, label=f"line {line}")
        for di, zz, num in zip(dist, xyz[:, 2],
                               d["Electrode number for survey"]):
            axe.annotate(str(num), (di, zz), fontsize=6, ha="center",
                         va="bottom", color=c)
    axe.set_xlabel("distance along line [m]"); axe.set_ylabel("Z height [m]")
    axe.grid(alpha=0.3); axe.legend(fontsize=9)
    axe.set_title("Electrode height (topography) along each line")

    fig.tight_layout()
    out = OUT / "electrode_layout_dem.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("saved", out)


if __name__ == "__main__":
    main()
