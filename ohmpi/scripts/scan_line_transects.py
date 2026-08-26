"""Elevation transect of each electrode line on the registered 24.05.30 scan.

For each line A-D: project electrodes onto their principal horizontal axis, sample
the scan DEM (via scan_dem) densely along that transect, and overlay each
electrode's scan-derived elevation. x = distance along line [m], y = elevation.

This replaces the old -Z_av topography; electrodes should now sit on the sampled
surface.
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import scan_dem  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ELEC_XLSX = REPO / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
OUT = REPO / "ohmpi" / "outputs" / "diagnostics" / "scan_line_transects.png"
LINES = ["A", "B", "C", "D"]


def line_electrodes(line: str):
    m = pl.read_excel(ELEC_XLSX).filter(pl.col("Line") == line)
    x = -m["X_av"].to_numpy()          # canonical world
    y = -m["Y_av"].to_numpy()
    ch = m["Ohmpi channel"].to_list()
    return np.column_stack([x, y]), ch


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scan_dem.build_grid()
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    for ax, line in zip(axes.ravel(), LINES):
        xy, ch = line_electrodes(line)
        c = xy.mean(0)
        axis = np.linalg.svd(xy - c)[2][0]
        along = (xy - c) @ axis
        order = np.argsort(along)
        along, ch = along[order], [ch[i] for i in order]
        xy = xy[order]
        s0 = along.min()
        along = along - s0
        # dense transect along the same world axis, sampled from the scan DEM
        s = np.linspace(along.min() - 0.5, along.max() + 0.5, 200)
        pts = c + np.outer(s + s0, axis)
        dem = scan_dem.elevation(pts[:, 0], pts[:, 1])
        elec_elev = scan_dem.elevation(xy[:, 0], xy[:, 1])

        ax.plot(s, dem, "-", color="0.4", lw=2, label="scan DEM along line")
        ax.plot(along, elec_elev, "o", ms=8, color="#1f77b4", mec="k",
                label="electrode (scan elevation)")
        for a, zz, cc in zip(along, elec_elev, ch):
            ax.annotate(str(cc), (a, zz), fontsize=7, xytext=(3, 4),
                        textcoords="offset points")
        ax.set_title(f"Line {line}", fontweight="bold")
        ax.set_xlabel("distance along line [m]")
        ax.set_ylabel("elevation (scan H) [m]")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="best")

    fig.suptitle("Electrode line transects on the registered 24.05.30 scan DEM",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(OUT, dpi=130, bbox_inches="tight")
    print("saved", OUT.relative_to(REPO))


if __name__ == "__main__":
    main()
