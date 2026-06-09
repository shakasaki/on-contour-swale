"""Planview visual check: electrode XY over the registered 24.05.30 scan DEM,
electrodes coloured by their *surveyed* Z_av on the SAME colormap as the DEM.

If a surveyed electrode height matches the surface beneath it, its dot colour
blends into the background. Dots that "pop" = electrode Z disagrees with the
scan surface there.

Vertical datum note: the scan↔survey registration is a 2-D similarity (XY only),
so the absolute vertical datums differ. Z_av is shifted by a single constant
(median match to the DEM at electrode XYs) so the colour compares topographic
*shape*, not an arbitrary offset. The shift applied is printed and shown.
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
OUT = REPO / "ohmpi" / "outputs" / "diagnostics" / "elec_z_vs_dem.png"
CMAP = "terrain"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scan_dem.build_grid()
    grid, (x0, x1, y0, y1), _ = scan_dem._load_grid()

    m = pl.read_excel(ELEC_XLSX)
    xw = -m["X_av"].to_numpy()          # canonical world
    yw = -m["Y_av"].to_numpy()
    z_av = m["Z_av"].to_numpy()
    line = m["Line"].to_list()
    ch = m["Ohmpi channel"].to_list()

    Xo, Yo = scan_dem.world_to_scan(xw, yw)
    dem_at_elec = scan_dem.elevation(xw, yw)

    # single-constant datum match (median of Z_av -> median DEM at electrodes)
    shift = float(np.nanmedian(dem_at_elec) - np.nanmedian(z_av))
    z_aligned = z_av + shift

    # shared colour scale from the DEM background (robust percentiles)
    finite = grid[np.isfinite(grid)]
    vmin, vmax = np.percentile(finite, [2, 98])

    fig, ax = plt.subplots(figsize=(11, 9))
    im = ax.imshow(grid.T, origin="lower", extent=(x0, x1, y0, y1),
                   cmap=CMAP, vmin=vmin, vmax=vmax, aspect="equal", alpha=0.85)
    sc = ax.scatter(Xo, Yo, c=z_aligned, cmap=CMAP, vmin=vmin, vmax=vmax,
                    s=90, edgecolor="k", linewidths=1.1, zorder=3)
    for X, Y, c, ln in zip(Xo, Yo, ch, line):
        ax.annotate(f"{ln}{c}", (X, Y), fontsize=6, xytext=(3, 3),
                    textcoords="offset points", zorder=4)

    cb = fig.colorbar(im, ax=ax, shrink=0.8)
    cb.set_label("elevation [m]  (DEM background = surveyed Z_av of dots)")
    ax.set_xlabel("scan-oriented Xo [m]")
    ax.set_ylabel("scan-oriented Yo [m]")
    ax.set_title(
        "Electrodes coloured by surveyed Z_av vs 24.05.30 scan DEM\n"
        f"(Z_av datum-shifted by {shift:+.3f} m to match DEM median; "
        "matching dots blend into the surface)",
        fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT, dpi=140, bbox_inches="tight")
    print("saved", OUT.relative_to(REPO))
    print(f"datum shift applied to Z_av: {shift:+.3f} m")
    # quick per-line residual summary (aligned Z_av - DEM)
    res = z_aligned - dem_at_elec
    print("per-line residual (aligned Z_av - DEM), mean / std [m]:")
    for ln in ["A", "B", "C", "D", "E"]:
        sel = [i for i, l in enumerate(line) if l == ln]
        if sel:
            r = res[sel]
            print(f"  {ln}: {r.mean():+.3f} / {r.std():.3f}  (n={len(sel)})")


if __name__ == "__main__":
    main()
