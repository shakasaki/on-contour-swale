"""Plot rotated survey-frame coordinates over the original DEM_2024_07_25 DEM.

This is a diagnostic/export script. It uses the original text DEM
``data/DEM/DEM_2024_07_25.txt`` and the raw ``X_av, Y_av`` coordinates
from ``data/SMS_locations.csv`` and the OhmPi electrode table, then
applies a 180-degree rotation ``(x, y) -> (-x, -y)`` to everything
before plotting.

Outputs land in ``plots/``:

* rotated plan-view figure
* rotated rasterized DEM XYZ export
* rotated sensor/landmark coordinate CSV
* rotated electrode coordinate CSV
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from scipy.interpolate import griddata

ROOT = Path(__file__).resolve().parent.parent

DEM = ROOT / "data" / "DEM" / "DEM_2024_07_25.txt"
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"
ELECTRODE_XLSX = (
    ROOT / "ohmpi" / "ohmpi_geometries" / "merged_electrode_table.xlsx"
)
OUT_PLOT = ROOT / "plots" / "12d_sensors_over_dem2024_rot180.png"
OUT_DEM_XYZ = ROOT / "plots" / "12d_dem2024_rot180_raster.xyz"
OUT_SENSOR_CSV = ROOT / "plots" / "12d_sensor_locations_rot180.csv"
OUT_ELECTRODE_CSV = ROOT / "plots" / "12d_electrode_locations_rot180.csv"

PLOT_MARGIN = 3.0   # around instruments for the cropped axes
HILLSHADE_N = 500

SWALE_COLOR = "#1f77b4"
CONTROL_COLOR = "#d62728"
LINE_COLORS = {
    "A": "tab:blue",
    "B": "tab:orange",
    "C": "tab:green",
    "D": "tab:red",
}  # line E excluded from paper figure

# Display names keyed by frozenset of SMS IDs
_DISPLAY_NAME: dict[frozenset, str] = {
    frozenset({"SMS01", "SMS02"}): "Top slope",
    frozenset({"SMS10"}): "Step",
    frozenset({"SMS03", "SMS04", "SMS05"}): "Mound",
    frozenset({"SMS06", "SMS07"}): "Bottom 1",
    frozenset({"SMS08", "SMS09"}): "Bottom 2",
    frozenset({"SMS11", "SMS12"}): "Top slope",
    frozenset({"SMS13", "SMS14"}): "Mid slope",
    frozenset({"SMS15", "SMS16"}): "Bottom slope",
}

# Per-label annotation offsets (points) to avoid crowding
_LABEL_OFFSET: dict[str, tuple[int, int]] = {
    "Top slope": (-70, 0),   # swale top — move left to avoid overlap with line B
    "Mound":     (-58, 0),   # left of marker, clear of Step
    "Step":      (6,   0),
    "Bottom 1":  (6,   6),
    "Bottom 2":  (6,  -8),
}


def parse_sensor_ids(label: str) -> tuple[str, ...]:
    """Parse the sensor ids from a CSV label cell."""
    quote_chars = "'\"‘’“”"
    raw = label.strip().strip(quote_chars)
    if not raw.upper().startswith("SMS"):
        return ()
    tail = raw[3:].strip()
    out = []
    for part in tail.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(f"SMS{int(part):02d}")
        except ValueError:
            continue
    return tuple(out)


def load_raw_locations():
    """Return raw-frame sensor pairs and landmarks from SMS_locations.csv."""
    records = []
    with LOCATIONS_CSV.open() as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                x = float(row[10])
                y = float(row[12])
                z = float(row[14])
            except (IndexError, ValueError):
                continue
            label = row[0].strip().strip("'\"‘’“”")
            records.append(
                {
                    "label": label,
                    "sensor_ids": parse_sensor_ids(label),
                    "x": x,
                    "y": y,
                    "z": z,
                }
            )
    return records


def rotate_xy_180(x, y):
    """Rotate survey coordinates 180 degrees about the origin."""
    return -np.asarray(x, dtype=float), -np.asarray(y, dtype=float)


def load_rotated_dem_points() -> np.ndarray:
    """Return DEM XYZ points after the 180-degree rotation."""
    d = np.loadtxt(DEM, usecols=(0, 1, 2))
    x_rot, y_rot = rotate_xy_180(d[:, 0], d[:, 1])
    return np.column_stack((x_rot, y_rot, d[:, 2]))


def rasterize_dem(
    dem_xyz: np.ndarray,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    n=HILLSHADE_N,
):
    """Grid the rotated DEM over [xlim, ylim]."""
    gx = np.linspace(*xlim, n)
    gy = np.linspace(*ylim, n)
    grid_x, grid_y = np.meshgrid(gx, gy)
    grid_z = griddata(
        dem_xyz[:, :2], dem_xyz[:, 2], (grid_x, grid_y), method="linear"
    )
    return grid_x, grid_y, grid_z


def dem_hillshade(grid_z: np.ndarray):
    """Return a greyscale hillshade [0,1]; NaN cells → 0.5 (neutral grey)."""
    nan_mask = ~np.isfinite(grid_z)
    filled = grid_z.copy()
    filled[nan_mask] = np.nanmean(grid_z)
    ls = LightSource(azdeg=315, altdeg=45)
    hs = ls.hillshade(filled, vert_exag=5)
    hs[nan_mask] = 0.5
    return hs


def export_raster_xyz(
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    grid_z: np.ndarray,
    out_path: Path,
) -> int:
    """Write the rasterized rotated DEM grid as XYZ rows."""
    mask = np.isfinite(grid_z)
    xyz = np.column_stack((grid_x[mask], grid_y[mask], grid_z[mask]))
    np.savetxt(
        out_path,
        xyz,
        fmt="%.6f",
        header="# Rotated DEM_2024_07_25 rasterized XYZ\n# x y z",
    )
    return int(xyz.shape[0])


def export_sensor_csv(records, out_path: Path) -> int:
    """Write rotated sensor and landmark coordinates as CSV."""
    rows = []
    for rec in records:
        x_rot, y_rot = rotate_xy_180(rec["x"], rec["y"])
        rows.append(
            {
                "label": rec["label"],
                "sensor_ids": "|".join(rec["sensor_ids"]),
                "kind": "sensor" if rec["sensor_ids"] else "landmark",
                "x_rot180": float(x_rot),
                "y_rot180": float(y_rot),
                "z": float(rec["z"]),
            }
        )
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_electrode_csv(electrode_table: pl.DataFrame, out_path: Path) -> int:
    """Write rotated electrode coordinates as CSV."""
    x_rot, y_rot = rotate_xy_180(
        electrode_table["X_av"].to_numpy(),
        electrode_table["Y_av"].to_numpy(),
    )
    out_df = electrode_table.select(
        "Line",
        "Electrode number for survey",
        "X_av",
        "Y_av",
        "Z_av",
    ).with_columns(
        pl.Series("x_rot180", x_rot),
        pl.Series("y_rot180", y_rot),
    )
    out_df.write_csv(out_path)
    return out_df.height


def main() -> None:
    OUT_PLOT.parent.mkdir(exist_ok=True)
    records = load_raw_locations()
    electrode_table = pl.read_excel(ELECTRODE_XLSX)
    dem_xyz = load_rotated_dem_points()
    sensors = [r for r in records if r["sensor_ids"]]
    landmarks = [r for r in records if not r["sensor_ids"]]

    x_all, y_all = rotate_xy_180(
        np.array([r["x"] for r in records], dtype=float),
        np.array([r["y"] for r in records], dtype=float),
    )
    # Crop to active instruments only (lines A–D + sensors); exclude line E
    active_elec = electrode_table.filter(pl.col("Line") != "E")
    ex_active, ey_active = rotate_xy_180(
        active_elec["X_av"].to_numpy(),
        active_elec["Y_av"].to_numpy(),
    )
    x_pts = np.concatenate([x_all, ex_active])
    y_pts = np.concatenate([y_all, ey_active])
    xlim = (float(x_pts.min()) - PLOT_MARGIN, float(x_pts.max()) + PLOT_MARGIN)
    ylim = (float(y_pts.min()) - PLOT_MARGIN, float(y_pts.max()) + PLOT_MARGIN)

    # Rasterize DEM over the plot extent only (faster + no edge NaN artifacts)
    grid_x, grid_y, grid_z = rasterize_dem(dem_xyz, xlim, ylim)
    rgb = dem_hillshade(grid_z)  # 2D greyscale [0,1]

    n_xyz = export_raster_xyz(grid_x, grid_y, grid_z, OUT_DEM_XYZ)
    n_sensor = export_sensor_csv(records, OUT_SENSOR_CSV)
    n_elec = export_electrode_csv(electrode_table, OUT_ELECTRODE_CSV)

    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(
        rgb,
        extent=(xlim[0], xlim[1], ylim[0], ylim[1]),
        origin="lower",
        cmap="gray",
        vmin=0.0,
        vmax=1.0,
        alpha=0.85,
        zorder=1,
    )

    for line, color in LINE_COLORS.items():
        d = electrode_table.filter(pl.col("Line") == line).sort(
            "Electrode number for survey"
        )
        if d.height == 0:
            continue
        x_plot, y_plot = rotate_xy_180(
            d["X_av"].to_numpy(),
            d["Y_av"].to_numpy(),
        )
        ax.plot(
            x_plot,
            y_plot,
            "-",
            color=color,
            lw=1.3,
            alpha=0.8,
            zorder=2,
            label=f"Electrode line {line}",
        )
        ax.scatter(
            x_plot,
            y_plot,
            s=55,
            color=color,
            edgecolor="black",
            linewidth=0.6,
            zorder=3,
        )

    landmark_style = {
        "weather station": ("*", "gold", "Weather station"),
        "left soil profile (closer to swale)": ("D", "saddlebrown", "Soil profile"),
        "right soil profile (further from swale)": ("D", "peru", "Soil profile"),
    }
    for lm in landmarks:
        style = landmark_style.get(str(lm["label"]).lower())
        if style is None:
            continue
        marker, color, short_label = style
        x_plot, y_plot = rotate_xy_180(lm["x"], lm["y"])
        ax.scatter(
            [x_plot],
            [y_plot],
            marker=marker,
            s=220,
            color=color,
            edgecolor="black",
            linewidth=1.1,
            zorder=3,
        )
        ax.annotate(
            short_label,
            (float(x_plot), float(y_plot)),
            xytext=(7, 7),
            textcoords="offset points",
            fontsize=8,
            bbox={
                "facecolor": "white",
                "alpha": 0.85,
                "edgecolor": "none",
                "boxstyle": "round,pad=0.18",
            },
            zorder=4,
        )

    for rec in sensors:
        ids = rec["sensor_ids"]
        treatment = "swale" if ids and ids[0] <= "SMS10" else "control"
        color = SWALE_COLOR if treatment == "swale" else CONTROL_COLOR
        marker = "o" if treatment == "swale" else "s"
        x_plot, y_plot = rotate_xy_180(rec["x"], rec["y"])
        ax.scatter(
            [x_plot],
            [y_plot],
            marker=marker,
            s=130,
            facecolors="white",
            edgecolors=color,
            linewidths=2.0,
            zorder=3,
        )
        display = _DISPLAY_NAME.get(frozenset(ids), ",".join(ids))
        dx, dy = _LABEL_OFFSET.get(display, (6, 0))
        ax.annotate(
            display,
            (float(x_plot), float(y_plot)),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=8,
            ha="left",
            va="center",
            color=color,
            bbox={
                "facecolor": "white",
                "alpha": 0.85,
                "edgecolor": "none",
                "boxstyle": "round,pad=0.18",
            },
            zorder=4,
        )

    legend_handles = [
        Line2D(
            [0], [0], marker="o", linestyle="none",
            markerfacecolor="white", markeredgecolor=SWALE_COLOR,
            markeredgewidth=2, markersize=9, label="Swale SMS pair",
        ),
        Line2D(
            [0], [0], marker="s", linestyle="none",
            markerfacecolor="white", markeredgecolor=CONTROL_COLOR,
            markeredgewidth=2, markersize=9, label="Control SMS pair",
        ),
        Line2D(
            [0], [0], marker="*", linestyle="none",
            markerfacecolor="gold", markeredgecolor="black",
            markersize=12, label="Weather station",
        ),
        Line2D(
            [0], [0], marker="D", linestyle="none",
            markerfacecolor="saddlebrown", markeredgecolor="black",
            markersize=8, label="Soil profile",
        ),
    ]
    legend_handles.extend(
        Line2D(
            [0], [0], color=color, lw=1.3, marker="o",
            markerfacecolor=color, markeredgecolor="black",
            markersize=6, label=f"ERT line {line}",
        )
        for line, color in LINE_COLORS.items()
    )
    ax.legend(
        handles=legend_handles,
        loc="upper right",
        fontsize=9,
        frameon=True,
    )
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    fig.tight_layout()
    fig.savefig(OUT_PLOT, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT_PLOT.relative_to(ROOT)}")
    print(f"wrote {OUT_DEM_XYZ.relative_to(ROOT)}  ({n_xyz:,} xyz rows)")
    print(f"wrote {OUT_SENSOR_CSV.relative_to(ROOT)}  ({n_sensor} rows)")
    print(f"wrote {OUT_ELECTRODE_CSV.relative_to(ROOT)}  ({n_elec} rows)")


if __name__ == "__main__":
    main()
