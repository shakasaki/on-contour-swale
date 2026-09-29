"""Elevation transect along the SMS soil-moisture sensors, swale vs control.

Mirrors ``ohmpi/scripts/scan_line_transects.py`` (electrode lines) but for the
SMS sensor pairs: project each treatment's sensor locations onto its
along-slope principal axis, sample the DEM_2024_07_25 point cloud (same DEM
and same 180-degree rotation as ``scripts/12d_sensors_over_dem2024.py``)
densely along that axis, and mark each sensor pair at its own (projected
distance, sampled elevation).

Also renders a plan-view companion (``13_sms_line_transects_planview.png``):
DEM_2024_07_25 hillshade with both transect lines, the SMS sensor pairs, and
electrode line A overlaid, to check the transect axis actually tracks the
sensors on the ground.

Outputs:
    plots/13_sms_line_transects.png
    plots/13_sms_line_transects_planview.png

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/13_sms_line_transects.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import LightSource
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator, griddata

from swale.sites import sensor_pairs

ROOT = Path(__file__).resolve().parent.parent
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"
DEM_TXT = ROOT / "data" / "DEM" / "DEM_2024_07_25.txt"
ELECTRODE_XLSX = ROOT / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
OUT_PNG = ROOT / "plots" / "13_sms_line_transects.png"
OUT_PLAN_PNG = ROOT / "plots" / "13_sms_line_transects_planview.png"

TREATMENT_COLOR = {"swale": "#1f77b4", "control": "#d62728"}
N_DENSE = 300
MARGIN_M = 1.0
PLAN_MARGIN_M = 3.0
PLAN_RASTER_N = 400


class MeshElevation:
    """Elevation(x, y) from the rotated DEM_2024_07_25 point cloud (linear, nearest fallback)."""

    def __init__(self, dem_txt: Path):
        d = np.loadtxt(dem_txt, usecols=(0, 1, 2))
        xy = np.column_stack((-d[:, 0], -d[:, 1]))  # same 180-deg rotation as 12d_
        z = d[:, 2]
        self._lin = LinearNDInterpolator(xy, z)
        self._near = NearestNDInterpolator(xy, z)

    def __call__(self, xy: np.ndarray) -> np.ndarray:
        z = self._lin(xy)
        nan = np.isnan(z)
        if nan.any():
            z[nan] = self._near(xy[nan])
        return z


def build_elevation_interpolator() -> MeshElevation:
    return MeshElevation(DEM_TXT)


def transect(pairs, treatment: str, elev: MeshElevation):
    """(dense_s, dense_z, along_pairs, z_pairs, labels) for one treatment's sensors."""
    sub = [p for p in pairs if p.treatment == treatment]
    xy = np.array([[p.x, p.y] for p in sub])
    c = xy.mean(0)
    axis = np.linalg.svd(xy - c)[2][0]
    along = (xy - c) @ axis
    order = np.argsort(along)
    sub = [sub[i] for i in order]
    along = along[order]
    s0 = along.min()
    along = along - s0

    s_dense = np.linspace(along.min() - MARGIN_M, along.max() + MARGIN_M, N_DENSE)
    pts = c + np.outer(s_dense + s0, axis)
    z_dense = elev(pts)

    xy_pairs = c + np.outer(along + s0, axis)
    z_pairs = elev(xy_pairs)
    labels = [f"{p.widmer_location}\n({'/'.join(p.sensor_ids)})" for p in sub]

    return s_dense, z_dense, along, z_pairs, labels, pts, xy_pairs


def load_line_a_electrodes() -> np.ndarray:
    """Rotated (x, y) for electrode Line A, ordered along the line."""
    m = pl.read_excel(ELECTRODE_XLSX).filter(pl.col("Line") == "A")
    x = -m["X_av"].to_numpy()
    y = -m["Y_av"].to_numpy()
    return np.column_stack([x, y])


def render_planview(pairs, transects: dict, dem_xy: np.ndarray, dem_z: np.ndarray) -> None:
    all_xy = np.vstack([t[5] for t in transects.values()])  # dense pts, both treatments
    x0, x1 = all_xy[:, 0].min() - PLAN_MARGIN_M, all_xy[:, 0].max() + PLAN_MARGIN_M
    y0, y1 = all_xy[:, 1].min() - PLAN_MARGIN_M, all_xy[:, 1].max() + PLAN_MARGIN_M

    gx, gy = np.meshgrid(np.linspace(x0, x1, PLAN_RASTER_N), np.linspace(y0, y1, PLAN_RASTER_N))
    gz = griddata(dem_xy, dem_z, (gx, gy), method="linear")
    finite = np.isfinite(gz)
    filled = np.where(finite, gz, np.nanmean(gz))
    # Relief here is shallow at this crop scale (~2-3 m over ~15-20 m) so a
    # plain grayscale hillshade has almost no contrast; color by elevation
    # (terrain cmap) blended with hillshade so the shape is actually visible.
    ls = LightSource(azdeg=315, altdeg=45)
    vmin, vmax = np.nanpercentile(filled, [2, 98])
    rgb = ls.shade(filled, cmap=plt.cm.terrain, vmin=vmin, vmax=vmax,
                    vert_exag=15, blend_mode="soft")

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(rgb, origin="lower", extent=(x0, x1, y0, y1), aspect="equal")

    for treatment, t in transects.items():
        _, _, along, z_pairs, labels, pts, xy_pairs = t
        color = TREATMENT_COLOR[treatment]
        ax.plot(pts[:, 0], pts[:, 1], "-", color=color, lw=2.5,
                 label=f"{treatment} transect axis", zorder=3)
        ax.scatter(xy_pairs[:, 0], xy_pairs[:, 1], s=90, color=color,
                    edgecolor="k", zorder=4)
        for (x, y), lab in zip(xy_pairs, labels):
            ax.annotate(lab.replace("\n", " "), (x, y), fontsize=7,
                        xytext=(5, 5), textcoords="offset points")

    line_a = load_line_a_electrodes()
    ax.plot(line_a[:, 0], line_a[:, 1], "s--", color="black", ms=5,
             lw=1.2, label="electrode Line A", zorder=2)

    ax.set_xlabel("X (m, canonical/rotated)")
    ax.set_ylabel("Y (m, canonical/rotated)")
    ax.set_title("Plan view: SMS transect axes vs electrode Line A, DEM_2024_07_25",
                  fontweight="bold")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT_PLAN_PNG, dpi=140, bbox_inches="tight")
    print(f"Wrote {OUT_PLAN_PNG.relative_to(ROOT)}")


def main() -> None:
    OUT_PNG.parent.mkdir(exist_ok=True)
    print("Loading DEM_2024_07_25 point cloud...")
    elev = build_elevation_interpolator()
    d = np.loadtxt(DEM_TXT, usecols=(0, 1, 2))
    dem_xy = np.column_stack((-d[:, 0], -d[:, 1]))
    dem_z = d[:, 2]

    pairs = sensor_pairs(LOCATIONS_CSV)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    transects = {}
    for ax, treatment in zip(axes, ["swale", "control"]):
        t = transect(pairs, treatment, elev)
        transects[treatment] = t
        s_dense, z_dense, along, z_pairs, labels, pts, xy_pairs = t
        color = TREATMENT_COLOR[treatment]
        ax.plot(s_dense, z_dense, "-", color="0.4", lw=2, label="DEM_2024_07_25")
        ax.plot(along, z_pairs, "o", ms=9, color=color, mec="k", zorder=3,
                label=f"{treatment} sensor pair")
        for a, z, lab in zip(along, z_pairs, labels):
            ax.annotate(lab, (a, z), fontsize=7.5, xytext=(4, 6),
                        textcoords="offset points", ha="left")
        ax.set_title(f"{treatment} transect", fontweight="bold")
        ax.set_xlabel("distance along transect [m]")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, loc="best")
    axes[0].set_ylabel("elevation [m] (DEM_2024_07_25, rotated 180°)")

    fig.suptitle("SMS sensor-pair elevation transects (swale vs control), DEM_2024_07_25",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight")
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")

    render_planview(pairs, transects, dem_xy, dem_z)


if __name__ == "__main__":
    main()
