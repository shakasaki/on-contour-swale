"""DEM visualisation: 2-D plan view + 3-D oblique view.

Reads ``data/DEM/Mesh_swale_site.vtk`` (cleaned triangulated mesh,
~27 k vertices / ~54 k faces) and produces:

* ``plots/12_dem_xy.png`` — top-down plan view rendered with
  matplotlib's ``tripcolor``, coloured by elevation. Sensor positions
  from ``data/SMS_locations.csv`` are overlaid to test whether the
  SMS_locations frame is already aligned with the DEM frame.
* ``plots/12_dem_3d.png`` — oblique 3-D view rendered with PyVista
  (off-screen), Z exaggerated 2× so the swale/mound geometry shows.
  Sensor pairs overlaid as spheres.

Outputs landed in ``plots/`` per project convention.

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/12_dem_views.py
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pyvista as pv

from swale.config import load_settings
from swale.sites import load_sensor_pairs, sensor_pairs
from swale.spatial_frame import load_canonical_dem_mesh

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()

DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"

OUT_XY = ROOT / "plots" / "12_dem_xy.png"
OUT_3D = ROOT / "plots" / "12_dem_3d.png"

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

Z_EXAG_3D = 2.0                    # vertical exaggeration in the 3-D view
SENSOR_SPHERE_RADIUS = 0.15        # radius for sensor markers in 3D (m)
CMAP = "terrain"                   # elevation colour map
DPI_XY = 220                       # 2-D plot DPI — push for detail
CONTOUR_INTERVAL_M = 0.10          # contour spacing in metres
CONTOUR_MAJOR_EVERY = 5            # every Nth contour gets the labelled style

# Camera for the 3D screenshot, in the canonical frame
# (+X = East, +Y = North). Looking from the south-west (negative X,
# negative Y) toward the sensor cluster (swale around X~-5, Y~-6).
# PyVista accepts (position, focal_point, view_up).
CAMERA_3D = [
    (-25.0, -25.0, 10.0),          # position: SW of the site, slightly elevated
    ( -3.0,  -4.0,  0.0),           # focal point near the sensor cluster
    (  0.0,   0.0,  1.0),           # view up
]


def load_mesh() -> pv.PolyData:
    """Load the site mesh in the canonical frame (+X=East, +Y=North)."""
    return load_canonical_dem_mesh(DEM_MESH)


# ---------------------------------------------------------------------------
# 2-D plan view
# ---------------------------------------------------------------------------

def plot_xy(mesh: pv.PolyData, out: Path) -> None:
    """Top-down view of the mesh, coloured by elevation, with sensors overlaid."""
    pts = np.asarray(mesh.points)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]

    # Extract triangle indices. PolyData.faces is a flat array of
    # [n_verts, v0, v1, ..., n_verts, v0, ...]. For a pure-triangle
    # mesh we can reshape (4, -1) then drop the leading 3s.
    faces = mesh.faces.reshape(-1, 4)
    if not np.all(faces[:, 0] == 3):
        raise RuntimeError("mesh has non-triangle faces; not supported here")
    tris = faces[:, 1:4]

    tri_obj = mtri.Triangulation(x, y, tris)

    fig, ax = plt.subplots(figsize=(11, 11))

    # shading="flat" colours each triangle by its mean Z — no interpolation.
    # That preserves the raw resolution of the mesh.
    tpc = ax.tripcolor(tri_obj, z, shading="flat", cmap=CMAP)
    cbar = fig.colorbar(tpc, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Elevation Z (m)")

    # Contour lines over the elevation field.
    z_min, z_max = z.min(), z.max()
    levels = np.arange(
        np.ceil(z_min / CONTOUR_INTERVAL_M) * CONTOUR_INTERVAL_M,
        z_max + CONTOUR_INTERVAL_M,
        CONTOUR_INTERVAL_M,
    )
    minor_levels = [lv for i, lv in enumerate(levels) if i % CONTOUR_MAJOR_EVERY != 0]
    major_levels = [lv for i, lv in enumerate(levels) if i % CONTOUR_MAJOR_EVERY == 0]
    if minor_levels:
        ax.tricontour(tri_obj, z, levels=minor_levels,
                       colors="black", linewidths=0.3, alpha=0.35)
    if major_levels:
        major_cs = ax.tricontour(tri_obj, z, levels=major_levels,
                                  colors="black", linewidths=0.7, alpha=0.6)
        ax.clabel(major_cs, inline=True, fontsize=7, fmt="%.1f")

    # All non-mesh markers come from SMS_locations.csv (sensors + landmarks).
    all_items = load_sensor_pairs(LOCATIONS_CSV)
    sms_only = sensor_pairs(LOCATIONS_CSV)
    landmarks = [p for p in all_items if not p.sensor_ids]

    swale_color = SETTINGS.treatment_colors.get("swale", "#1f77b4")
    control_color = SETTINGS.treatment_colors.get("control", "#d62728")

    # Soil profiles and weather station as star/diamond markers.
    LANDMARK_STYLE = {
        "weather station":                          ("*", "gold",       "Weather station"),
        "left soil profile (closer to swale)":      ("D", "saddlebrown", "Soil profile (swale-side)"),
        "right soil profile (further from swale)":  ("D", "peru",        "Soil profile (control-side)"),
    }
    for lm in landmarks:
        style = LANDMARK_STYLE.get(lm.label.lower())
        if style is None:
            continue
        marker, color, _ = style
        ax.scatter([lm.x], [lm.y], marker=marker, s=260,
                   facecolors=color, edgecolors="black", linewidths=1.2, zorder=4)
        ax.annotate(
            lm.label, xy=(lm.x, lm.y),
            xytext=(8, 8), textcoords="offset points",
            fontsize=8, ha="left", va="bottom", color="black",
            bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none",
                  "boxstyle": "round,pad=0.2"},
            zorder=5,
        )

    # SMS pairs.
    for p in sms_only:
        marker = "o" if p.treatment == "swale" else "s"
        color = swale_color if p.treatment == "swale" else control_color
        ax.scatter([p.x], [p.y], marker=marker, s=130,
                   facecolors="white", edgecolors=color,
                   linewidths=2.0, zorder=4)
        ids = ",".join(sid.replace("SMS", "") for sid in p.sensor_ids)
        dx_px = -50 if p.x > 0 else 50
        ha = "right" if dx_px < 0 else "left"
        ax.annotate(
            f"SMS {ids}", xy=(p.x, p.y),
            xytext=(dx_px, 0), textcoords="offset points",
            fontsize=8, ha=ha, va="center", color=color,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none",
                  "boxstyle": "round,pad=0.2"},
            zorder=5,
        )

    # Legend
    sz = np.array([p.z for p in sms_only])
    legend_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none",
                   markerfacecolor="white", markeredgecolor=swale_color,
                   markersize=10, markeredgewidth=2, label="Swale SMS pair"),
        plt.Line2D([0], [0], marker="s", linestyle="none",
                   markerfacecolor="white", markeredgecolor=control_color,
                   markersize=10, markeredgewidth=2, label="Control SMS pair"),
        plt.Line2D([0], [0], marker="*", linestyle="none",
                   markerfacecolor="gold", markeredgecolor="black",
                   markersize=14, label="Weather station"),
        plt.Line2D([0], [0], marker="D", linestyle="none",
                   markerfacecolor="saddlebrown", markeredgecolor="black",
                   markersize=10, label="Soil profile"),
    ]
    ax.legend(handles=legend_handles, loc="upper right",
              fontsize=9, frameon=True, framealpha=0.95)

    ax.set_xlabel("X (m, canonical frame; +X = East)")
    ax.set_ylabel("Y (m, canonical frame; +Y = North)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.20)
    ax.set_title(
        "Mesh_swale_site.vtk — plan view, coloured by elevation\n"
        f"Sensors + soil profiles + weather station; "
        f"DEM Z [{z.min():+.2f}, {z.max():+.2f}] m; "
        f"contours every {CONTOUR_INTERVAL_M:.2f} m "
        f"(major every {CONTOUR_MAJOR_EVERY * CONTOUR_INTERVAL_M:.2f} m)",
        fontsize=10.5,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=DPI_XY)
    plt.close(fig)
    print(f"  wrote {out.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# 3-D oblique view via PyVista
# ---------------------------------------------------------------------------

def plot_3d(mesh: pv.PolyData, out: Path) -> None:
    """Oblique 3-D view with elevation colouring and sensor spheres."""
    pv.OFF_SCREEN = True

    # Vertical exaggeration: scale Z to make the swale/mound visible.
    work = mesh.copy()
    work.points[:, 2] *= Z_EXAG_3D
    work["Elevation"] = work.points[:, 2] / Z_EXAG_3D  # show true elevation in cbar

    p = pv.Plotter(off_screen=True, window_size=(1400, 1000))
    p.add_mesh(work, scalars="Elevation", cmap=CMAP,
               scalar_bar_args={"title": "Elevation Z (m)"},
               show_edges=False, smooth_shading=True)

    pairs = sensor_pairs(LOCATIONS_CSV)
    swale_color = SETTINGS.treatment_colors.get("swale", "#1f77b4")
    control_color = SETTINGS.treatment_colors.get("control", "#d62728")
    for pair in pairs:
        # Lift the sphere slightly above the local Z so it doesn't sink
        # into the mesh. Using the SMS_locations Z (after our sign-flip)
        # places it near the surface; +0.1 m gives it visible relief.
        sphere = pv.Sphere(
            radius=SENSOR_SPHERE_RADIUS,
            center=(pair.x, pair.y, (pair.z + 0.1) * Z_EXAG_3D),
        )
        p.add_mesh(sphere,
                   color=swale_color if pair.treatment == "swale" else control_color)

    p.add_text(f"Z exaggerated x{Z_EXAG_3D:.0f}",
               position="upper_left", font_size=11)
    p.show_axes()
    p.camera_position = CAMERA_3D

    p.screenshot(str(out))
    p.close()
    print(f"  wrote {out.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_XY.parent.mkdir(exist_ok=True)
    print(f"Loading {DEM_MESH.relative_to(ROOT)} ...")
    mesh = load_mesh()
    print(f"  {mesh.n_points:,} points / {mesh.n_cells:,} triangles")
    print(f"  bounds X[{mesh.bounds[0]:+.1f} {mesh.bounds[1]:+.1f}]  "
          f"Y[{mesh.bounds[2]:+.1f} {mesh.bounds[3]:+.1f}]  "
          f"Z[{mesh.bounds[4]:+.2f} {mesh.bounds[5]:+.2f}]")

    print("Plan view ...")
    plot_xy(mesh, OUT_XY)

    print("3-D view ...")
    plot_3d(mesh, OUT_3D)


if __name__ == "__main__":
    main()
