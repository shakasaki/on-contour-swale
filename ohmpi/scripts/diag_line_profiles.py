"""Diagnostic: DEM elevation cut along each electrode line vs surveyed Z.

For each line A-D, project the line's electrodes onto their principal horizontal
axis, sample the LiDAR DEM densely along that transect, and plot:
  x = distance along the line [m], y = elevation [m]
  solid grey  : DEM surface sampled along the transect
  filled dots : electrode surveyed raw Z_av (at their along-line position)
  open dots   : electrode -Z_av (the value the inversion currently uses)

This shows directly whether the surveyed electrode elevations follow the measured
surface, with which sign, and exposes isolated bad points (e.g. line-A ch3).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import griddata

import sys

sys.path.insert(0, str(Path(__file__).parent))
from diag_dem_elevation_check import load_dem, rot180  # noqa: E402

import polars as pl  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ELEC_XLSX = REPO / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
OUT = REPO / "ohmpi" / "outputs" / "diagnostics" / "line_elevation_profiles.png"

LINES = ["A", "B", "C", "D"]


def line_electrodes(line: str):
    """Canonical-frame (x, y, raw Z_av, channel) for a line's electrodes, ordered."""
    m = pl.read_excel(ELEC_XLSX).filter(pl.col("Line") == line)
    x, y = rot180(m["X_av"].to_numpy(), m["Y_av"].to_numpy())
    z = m["Z_av"].to_numpy()
    ch = m["Ohmpi channel"].to_list()
    return np.column_stack([x, y]), z, ch


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dx, dy, dz = load_dem()
    demxy = np.column_stack([dx, dy])

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    for ax, line in zip(axes.ravel(), LINES):
        xy, z, ch = line_electrodes(line)
        c = xy.mean(0)
        axis = np.linalg.svd(xy - c)[2][0]
        raw_along = (xy - c) @ axis
        raw_min = raw_along.min()
        order = np.argsort(raw_along)
        along = raw_along[order] - raw_min          # shifted to start at 0
        z, ch = z[order], [ch[i] for i in order]
        # dense transect along the same axis, sampled from the DEM.
        # shifted distance s maps back to canonical xy via raw_along = s + raw_min.
        s = np.linspace(along.min() - 0.3, along.max() + 0.3, 200)
        pts = c + np.outer(s + raw_min, axis)
        dem_prof = griddata(demxy, dz, pts, method="linear")

        ax.plot(s, dem_prof, "-", color="0.4", lw=2, label="DEM along line")
        ax.plot(along, z, "o", ms=8, color="#1f77b4", mec="k",
                label="electrode raw Z_av")
        ax.plot(along, -z, "o", ms=8, mfc="none", color="#d62728",
                label="electrode -Z_av (current)")
        for a, zz, cc in zip(along, z, ch):
            ax.annotate(str(cc), (a, zz), fontsize=7, xytext=(3, 4),
                        textcoords="offset points")
        ax.set_title(f"Line {line}", fontweight="bold")
        ax.set_xlabel("distance along line [m]")
        ax.set_ylabel("elevation [m]")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="best")

    fig.suptitle("DEM elevation cut along each line vs surveyed electrode Z "
                 "(raw Z_av tracks the DEM; -Z_av is flipped)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT, dpi=130, bbox_inches="tight")
    print("saved", OUT.relative_to(REPO))


if __name__ == "__main__":
    main()
