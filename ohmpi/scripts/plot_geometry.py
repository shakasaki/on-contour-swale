"""Electrode layout figure: plan view over the DEM hillshade + an elevation panel.

Coordinate frame: the raw electrode survey X_av/Y_av require a 180° rotation
(x,y)→(−x,−y) to match the DEM and the rest of the project's canonical frame
(+X=East, +Y=North). This rotation is the same as 12d applies. The Z_av sign
is still inverted in the source table (more negative = higher in reality; fix
pending in merged_electrode_table.xlsx), so the elevation panel negates Z to
show true relative height with B upslope and E downslope.

Left  : plan view. DEM hillshade at 0.5 opacity; electrodes coloured by line,
        labelled by survey electrode number (1–50). OhmPi channel numbers (used
        in quad a/b/m/n) map to survey numbers via merged_electrode_table.xlsx.
Right : elevation — electrode height (−Z_av) vs distance along each line.
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
DEM  = REPO / "data" / "DEM" / "DEM_2024_07_25.txt"
OUT  = REPO / "ohmpi" / "plots" / "geometry"
OUT.mkdir(parents=True, exist_ok=True)

LINE_COLORS = {"A": "tab:blue", "B": "tab:orange", "C": "tab:green",
               "D": "tab:red",  "E": "tab:purple"}
MARGIN = 2.0


def rot180(x, y):
    return -np.asarray(x, float), -np.asarray(y, float)


def dem_hillshade(dem_xy: np.ndarray, dem_z: np.ndarray,
                  xlim, ylim, n=400):
    gx = np.linspace(*xlim, n)
    gy = np.linspace(*ylim, n)
    GX, GY = np.meshgrid(gx, gy)
    GZ = griddata(dem_xy, dem_z, (GX, GY), method="linear")
    ls = LightSource(azdeg=315, altdeg=45)
    return ls.shade(np.ma.masked_invalid(GZ), cmap=plt.cm.gray,
                    vert_exag=3, blend_mode="soft")


def main() -> None:
    m = pl.read_excel(GEOM)

    # apply 180° rotation to XY to match DEM / canonical frame
    rx, ry = rot180(m["X_av"].to_numpy(), m["Y_av"].to_numpy())
    # negate Z_av: stored inverted (more negative = higher in reality)
    rz = -m["Z_av"].to_numpy()

    xlim = (rx.min() - MARGIN, rx.max() + MARGIN)
    ylim = (ry.min() - MARGIN, ry.max() + MARGIN)

    # load + rotate DEM points
    d = np.loadtxt(DEM, usecols=(0, 1, 2))
    dx, dy = rot180(d[:, 0], d[:, 1])
    dz = d[:, 2]
    rgb = dem_hillshade(np.c_[dx, dy], dz, xlim, ylim)

    lines = m["Line"].to_numpy()
    surv  = m["Electrode number for survey"].to_numpy()

    fig, (axp, axe) = plt.subplots(1, 2, figsize=(16, 7),
                                   gridspec_kw={"width_ratios": [1.4, 1]})

    # --- plan view ---
    axp.imshow(rgb, extent=[*xlim, *ylim], origin="lower", alpha=0.5, zorder=1)
    for line, c in LINE_COLORS.items():
        g = lines == line
        order = np.argsort(surv[g])
        axp.plot(rx[g][order], ry[g][order], "-", color=c, lw=1.2,
                 alpha=0.7, zorder=2, label=f"line {line}")
        axp.scatter(rx[g][order], ry[g][order], s=90, color=c,
                    edgecolor="k", zorder=3)
    for num, xx, yy in zip(surv, rx, ry):
        axp.annotate(str(num), (xx, yy), fontsize=6, ha="center",
                     va="center", zorder=4, color="white", weight="bold")
    axp.set_xlim(xlim); axp.set_ylim(ylim); axp.set_aspect("equal")
    axp.set_xlabel("X [m, rotated frame]"); axp.set_ylabel("Y [m, rotated frame]")
    axp.legend(loc="upper right", fontsize=9)
    axp.set_title("Electrode layout over DEM hillshade (survey electrode no.)")

    # --- elevation: −Z_av (true relative height) along each line ---
    for line, c in LINE_COLORS.items():
        g = lines == line
        order = np.argsort(surv[g])
        xs, ys, zs = rx[g][order], ry[g][order], rz[g][order]
        dist = np.concatenate([[0], np.cumsum(
            np.linalg.norm(np.diff(np.c_[xs, ys], axis=0), axis=1))])
        axe.plot(dist, zs, "o-", color=c, ms=5, label=f"line {line}")
        for di, zz, num in zip(dist, zs, surv[g][order]):
            axe.annotate(str(num), (di, zz), fontsize=6, ha="center",
                         va="bottom", color=c)
    axe.set_xlabel("distance along line [m]")
    axe.set_ylabel("relative height (−Z_av) [m]")
    axe.grid(alpha=0.3); axe.legend(fontsize=9)
    axe.set_title("Electrode height along each line (B upslope, E downslope)")

    fig.tight_layout()
    out = OUT / "electrode_layout_dem.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print("saved", out)


if __name__ == "__main__":
    main()
