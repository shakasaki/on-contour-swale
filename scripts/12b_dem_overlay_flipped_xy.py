"""Sweep all 8 swap/sign transforms for overlay coordinates against the DEM.

Produces two multi-panel diagnostic figures over the averaged DEM:

* ``plots/12b_dem_xy_sensors_transform_sweep.png`` — sensor pairs,
    soil profiles, and the weather station for transforms A-H.
* ``plots/12c_dem_xy_electrodes_transform_sweep.png`` — electrode lines
    and positions for the same transforms A-H.

Also writes ``plots/12d_overlay_transform_table.csv`` listing the exact
mapping used in each panel so the visually correct frame can be chosen.

The DEM stays fixed. Each panel changes only the non-DEM overlay
coordinates using one of the 8 combinations of axis swap and sign flips:

        x' = sx * (swap ? y : x)
        y' = sy * (swap ? x : y)
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import polars as pl
import pyvista as pv
from matplotlib.lines import Line2D

from swale.config import load_settings
from swale.sites import load_sensor_pairs, sensor_pairs
from swale.spatial_frame import load_canonical_dem_mesh

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()

AVERAGED_DEM_MESH = (
    ROOT / "data" / "DEM" / "Mesh_swale_site_from_xyz_average.vtk"
)
LEGACY_DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"
ELECTRODE_XLSX = (
    ROOT / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
)

OUT_SENSORS = ROOT / "plots" / "12b_dem_xy_sensors_transform_sweep.png"
OUT_ELECTRODES = ROOT / "plots" / "12c_dem_xy_electrodes_transform_sweep.png"
OUT_TABLE = ROOT / "plots" / "12d_overlay_transform_table.csv"

CMAP = "terrain"
DPI = 220
CONTOUR_INTERVAL_M = 0.10
CONTOUR_MAJOR_EVERY = 5
LINE_COLORS = {
    "A": "tab:blue",
    "B": "tab:orange",
    "C": "tab:green",
    "D": "tab:red",
    "E": "tab:purple",
}

TRANSFORMS = [
    {"label": "A", "swap": False, "sx": 1, "sy": 1, "expr": "( x,  y)"},
    {"label": "B", "swap": False, "sx": -1, "sy": 1, "expr": "(-x,  y)"},
    {"label": "C", "swap": False, "sx": 1, "sy": -1, "expr": "( x, -y)"},
    {"label": "D", "swap": False, "sx": -1, "sy": -1, "expr": "(-x, -y)"},
    {"label": "E", "swap": True, "sx": 1, "sy": 1, "expr": "( y,  x)"},
    {"label": "F", "swap": True, "sx": -1, "sy": 1, "expr": "(-y,  x)"},
    {"label": "G", "swap": True, "sx": 1, "sy": -1, "expr": "( y, -x)"},
    {"label": "H", "swap": True, "sx": -1, "sy": -1, "expr": "(-y, -x)"},
]


def load_mesh() -> pv.PolyData:
    """Load the DEM mesh already used for the current plan-view outputs."""
    if AVERAGED_DEM_MESH.exists():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return cast(pv.PolyData, pv.read(AVERAGED_DEM_MESH))
    return load_canonical_dem_mesh(LEGACY_DEM_MESH)


def transform_xy(
    x: np.ndarray | float,
    y: np.ndarray | float,
    *,
    swap: bool,
    sx: int,
    sy: int,
):
    """Apply one swap/sign transform to overlay coordinates."""
    x_arr = np.asarray(x)
    y_arr = np.asarray(y)
    if swap:
        return sx * y_arr, sy * x_arr
    return sx * x_arr, sy * y_arr


def mesh_triangulation(
    mesh: pv.PolyData,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return x, y, z, tris for a triangle PolyData mesh."""
    pts = np.asarray(mesh.points)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    faces = mesh.faces.reshape(-1, 4)
    if not np.all(faces[:, 0] == 3):
        raise RuntimeError("mesh has non-triangle faces; not supported here")
    tris = faces[:, 1:4]
    return x, y, z, tris


def plot_dem_base(ax, mesh: pv.PolyData):
    """Draw filled DEM triangles and contour lines."""
    x, y, z, tris = mesh_triangulation(mesh)
    tri_obj = mtri.Triangulation(x, y, tris)
    tpc = ax.tripcolor(tri_obj, z, shading="flat", cmap=CMAP)

    levels = np.arange(
        np.ceil(z.min() / CONTOUR_INTERVAL_M) * CONTOUR_INTERVAL_M,
        z.max() + CONTOUR_INTERVAL_M,
        CONTOUR_INTERVAL_M,
    )
    minor_levels = [
        lv for i, lv in enumerate(levels)
        if i % CONTOUR_MAJOR_EVERY != 0
    ]
    major_levels = [
        lv for i, lv in enumerate(levels)
        if i % CONTOUR_MAJOR_EVERY == 0
    ]
    if minor_levels:
        ax.tricontour(
            tri_obj,
            z,
            levels=minor_levels,
            colors="black",
            linewidths=0.3,
            alpha=0.35,
        )
    if major_levels:
        major_cs = ax.tricontour(
            tri_obj,
            z,
            levels=major_levels,
            colors="black",
            linewidths=0.7,
            alpha=0.6,
        )
        ax.clabel(major_cs, inline=True, fontsize=7, fmt="%.1f")
    return tpc, z


def finish_axes(ax, title: str) -> None:
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.20)
    ax.set_title(title, fontsize=10)


def sensor_overlay_data():
    """Load sensor and landmark overlay inputs once."""
    all_items = load_sensor_pairs(LOCATIONS_CSV)
    sms_only = sensor_pairs(LOCATIONS_CSV)
    landmarks = [p for p in all_items if not p.sensor_ids]
    return sms_only, landmarks


def electrode_overlay_data() -> pl.DataFrame:
    """Load electrode geometry once."""
    return pl.read_excel(ELECTRODE_XLSX)


def add_sensor_overlay(ax, transform: dict, sms_only, landmarks) -> None:
    """Add transformed sensors + landmarks to one subplot."""
    swale_color = SETTINGS.treatment_colors.get("swale", "#1f77b4")
    control_color = SETTINGS.treatment_colors.get("control", "#d62728")
    landmark_style = {
        "weather station": ("*", "gold"),
        "left soil profile (closer to swale)": ("D", "saddlebrown"),
        "right soil profile (further from swale)": ("D", "peru"),
    }

    for lm in landmarks:
        style = landmark_style.get(lm.label.lower())
        if style is None:
            continue
        marker, color = style
        x_plot, y_plot = transform_xy(
            lm.x,
            lm.y,
            swap=transform["swap"],
            sx=transform["sx"],
            sy=transform["sy"],
        )
        ax.scatter(
            [x_plot],
            [y_plot],
            marker=marker,
            s=260,
            facecolors=color,
            edgecolors="black",
            linewidths=1.2,
            zorder=4,
        )
        ax.annotate(
            lm.label,
            xy=(float(x_plot), float(y_plot)),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=8,
            ha="left",
            va="bottom",
            color="black",
            bbox={
                "facecolor": "white",
                "alpha": 0.9,
                "edgecolor": "none",
                "boxstyle": "round,pad=0.2",
            },
            zorder=5,
        )

    for pair in sms_only:
        marker = "o" if pair.treatment == "swale" else "s"
        color = swale_color if pair.treatment == "swale" else control_color
        x_plot, y_plot = transform_xy(
            pair.x,
            pair.y,
            swap=transform["swap"],
            sx=transform["sx"],
            sy=transform["sy"],
        )
        ax.scatter(
            [x_plot],
            [y_plot],
            marker=marker,
            s=130,
            facecolors="white",
            edgecolors=color,
            linewidths=2.0,
            zorder=4,
        )
        ids = ",".join(sid.replace("SMS", "") for sid in pair.sensor_ids)
        dx_px = -50 if float(x_plot) > 0 else 50
        ha = "right" if dx_px < 0 else "left"
        ax.annotate(
            f"SMS {ids}",
            xy=(float(x_plot), float(y_plot)),
            xytext=(dx_px, 0),
            textcoords="offset points",
            fontsize=8,
            ha=ha,
            va="center",
            color=color,
            bbox={
                "facecolor": "white",
                "alpha": 0.85,
                "edgecolor": "none",
                "boxstyle": "round,pad=0.2",
            },
            zorder=5,
        )


def sensor_legend_handles():
    swale_color = SETTINGS.treatment_colors.get("swale", "#1f77b4")
    control_color = SETTINGS.treatment_colors.get("control", "#d62728")

    return [
        Line2D(
            [0], [0], marker="o", linestyle="none",
            markerfacecolor="white", markeredgecolor=swale_color,
            markersize=10, markeredgewidth=2, label="Swale SMS pair",
        ),
        Line2D(
            [0], [0], marker="s", linestyle="none",
            markerfacecolor="white", markeredgecolor=control_color,
            markersize=10, markeredgewidth=2, label="Control SMS pair",
        ),
        Line2D(
            [0], [0], marker="*", linestyle="none",
            markerfacecolor="gold", markeredgecolor="black",
            markersize=14, label="Weather station",
        ),
        Line2D(
            [0], [0], marker="D", linestyle="none",
            markerfacecolor="saddlebrown", markeredgecolor="black",
            markersize=10, label="Soil profile",
        ),
    ]


def add_electrode_overlay(ax, transform: dict, m: pl.DataFrame) -> None:
    """Add transformed electrode lines + nodes to one subplot."""
    for line, color in LINE_COLORS.items():
        d = m.filter(pl.col("Line") == line).sort(
            "Electrode number for survey"
        )
        if d.height == 0:
            continue
        x_plot, y_plot = transform_xy(
            d["X_av"].to_numpy(),
            d["Y_av"].to_numpy(),
            swap=transform["swap"],
            sx=transform["sx"],
            sy=transform["sy"],
        )
        ax.plot(
            x_plot,
            y_plot,
            "-",
            color=color,
            lw=1.2,
            alpha=0.8,
            zorder=3,
            label=f"line {line}",
        )
        ax.scatter(
            x_plot,
            y_plot,
            s=90,
            color=color,
            edgecolor="k",
            zorder=4,
        )
        for num, xx, yy in zip(
            d["Electrode number for survey"].to_list(),
            x_plot,
            y_plot,
        ):
            ax.annotate(
                str(num),
                (float(xx), float(yy)),
                fontsize=6,
                ha="center",
                va="center",
                zorder=5,
                color="white",
                weight="bold",
            )


def render_transform_sweep(
    mesh: pv.PolyData,
    out: Path,
    *,
    overlay_kind: str,
) -> None:
    """Render 8 transform variants in a labelled 2x4 figure."""
    fig, axes = plt.subplots(2, 4, figsize=(24, 12), sharex=True, sharey=True)
    axes_flat = axes.ravel()
    sms_only, landmarks = sensor_overlay_data()
    electrodes = electrode_overlay_data()

    tpc = None
    z_vals = None
    for ax, transform in zip(axes_flat, TRANSFORMS):
        tpc, z_vals = plot_dem_base(ax, mesh)
        if overlay_kind == "sensors":
            add_sensor_overlay(ax, transform, sms_only, landmarks)
        else:
            add_electrode_overlay(ax, transform, electrodes)
        finish_axes(
            ax,
            f"{transform['label']}: x', y' = {transform['expr']}",
        )

    if tpc is None or z_vals is None:
        raise RuntimeError("no transform panels were rendered")

    cbar = fig.colorbar(
        tpc,
        ax=axes_flat,
        shrink=0.82,
        pad=0.015,
    )
    cbar.set_label("Elevation Z (m)")

    if overlay_kind == "sensors":
        fig.legend(
            handles=sensor_legend_handles(),
            loc="lower center",
            bbox_to_anchor=(0.5, 0.01),
            ncol=4,
            fontsize=10,
            frameon=True,
        )
        title = (
            "Sensor / landmark overlay transform sweep over averaged DEM\n"
            f"DEM Z [{z_vals.min():+.2f}, {z_vals.max():+.2f}] m"
        )
    else:
        title = (
            "Electrode overlay transform sweep over averaged DEM\n"
            f"DEM Z [{z_vals.min():+.2f}, {z_vals.max():+.2f}] m"
        )
    fig.suptitle(title, fontsize=15, y=0.98)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def write_transform_table(out: Path) -> None:
    """Write the panel-to-transform lookup table as CSV."""
    out.parent.mkdir(parents=True, exist_ok=True)
    header = "label,swap_axes,negate_xprime,negate_yprime,expression\n"
    rows = [
        (
            f"{t['label']},{int(t['swap'])},{int(t['sx'] < 0)},"
            f"{int(t['sy'] < 0)},\"{t['expr']}\"\n"
        )
        for t in TRANSFORMS
    ]
    out.write_text(header + "".join(rows))


def main() -> None:
    OUT_SENSORS.parent.mkdir(exist_ok=True)
    mesh = load_mesh()
    print(
        f"Loaded DEM mesh with {mesh.n_points:,} points and "
        f"{mesh.n_cells:,} triangles"
    )

    print("Writing transform lookup table ...")
    write_transform_table(OUT_TABLE)
    print(f"  wrote {OUT_TABLE.relative_to(ROOT)}")

    print("Plotting sensor and landmark transform sweep ...")
    render_transform_sweep(mesh, OUT_SENSORS, overlay_kind="sensors")
    print(f"  wrote {OUT_SENSORS.relative_to(ROOT)}")

    print("Plotting electrode transform sweep ...")
    render_transform_sweep(mesh, OUT_ELECTRODES, overlay_kind="electrodes")
    print(f"  wrote {OUT_ELECTRODES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
