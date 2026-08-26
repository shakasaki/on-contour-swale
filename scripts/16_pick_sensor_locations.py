"""Interactive picker for soil-moisture sensor locations over the DEM.

Renders the DEM_2024_07_25 hillshade in the canonical frame
(+X=East, +Y=North) and overlays every SMS station from
``data/SMS_locations.csv`` (via :func:`swale.sites.sensor_pairs`, so any
edit to that file is reflected here). Each station marker is
**draggable**: click-and-drag it to its true position on the terrain.

Controls
--------
* drag a marker  -> move that station; its label follows.
* ``s``          -> save current positions to
                    ``plots/picked_sensor_locations.csv`` (canonical AND
                    raw frame; paste the raw X/Y into the ``X_av``/``Y_av``
                    columns of ``SMS_locations.csv``).
* ``r``          -> reset all stations to their original positions.

This needs an interactive matplotlib backend (TkAgg / QtAgg). Run it
from a terminal that can open a window, from the project root::

    PYTHONPATH=src .venv/bin/python scripts/16_pick_sensor_locations.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource
from scipy.interpolate import griddata

from swale.sites import default_locations_csv, sensor_pairs
from swale.spatial_frame import to_canonical_xy

ROOT = Path(__file__).resolve().parent.parent
DEM = ROOT / "data" / "DEM" / "DEM_2024_07_25.txt"
LOCATIONS_CSV = default_locations_csv()
OUT_CSV = ROOT / "plots" / "picked_sensor_locations.csv"

MARGIN = 2.0
HILLSHADE_N = 400
PICK_RADIUS_M = 0.6  # how close a click must be (data units) to grab a marker

SWALE_COLOR = "#1f77b4"
CONTROL_COLOR = "#d62728"


def dem_hillshade_image(xlim, ylim):
    """Rasterize the canonical-frame DEM and return (rgb, extent)."""
    d = np.loadtxt(DEM, usecols=(0, 1, 2))
    x, y = to_canonical_xy(d[:, 0], d[:, 1])
    gx = np.linspace(*xlim, HILLSHADE_N)
    gy = np.linspace(*ylim, HILLSHADE_N)
    grid_x, grid_y = np.meshgrid(gx, gy)
    grid_z = griddata(
        np.column_stack((x, y)), d[:, 2], (grid_x, grid_y), method="linear"
    )
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(
        np.ma.masked_invalid(grid_z),
        cmap=plt.get_cmap("terrain"),
        vert_exag=3,
        blend_mode="soft",
    )
    return rgb


def main() -> None:
    pairs = sensor_pairs(LOCATIONS_CSV)
    x0 = np.array([p.x for p in pairs], dtype=float)
    y0 = np.array([p.y for p in pairs], dtype=float)
    labels = [",".join(s.replace("SMS", "") for s in p.sensor_ids) for p in pairs]
    colors = [SWALE_COLOR if p.treatment == "swale" else CONTROL_COLOR for p in pairs]

    xlim = (x0.min() - MARGIN, x0.max() + MARGIN)
    ylim = (y0.min() - MARGIN, y0.max() + MARGIN)
    rgb = dem_hillshade_image(xlim, ylim)

    # Mutable working copy of the positions.
    xy = np.column_stack((x0, y0))

    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(rgb, extent=(*xlim, *ylim), origin="lower", alpha=0.7, zorder=1)
    scat = ax.scatter(
        xy[:, 0], xy[:, 1], s=160, facecolors="white",
        edgecolors=colors, linewidths=2.2, zorder=3, picker=True,
    )
    annots = [
        ax.annotate(
            f"SMS {lab}", (xy[i, 0], xy[i, 1]),
            xytext=(7, 0), textcoords="offset points",
            fontsize=8, ha="left", va="center", color=colors[i], zorder=4,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none",
                  "boxstyle": "round,pad=0.18"},
        )
        for i, lab in enumerate(labels)
    ]

    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.set_xlabel("X (m, canonical frame; +X = East)")
    ax.set_ylabel("Y (m, canonical frame; +Y = North)")
    ax.set_title(
        "Drag SMS markers to true positions  |  s = save CSV  |  r = reset"
    )

    state = {"drag": None}  # index of the marker currently being dragged

    def redraw():
        scat.set_offsets(xy)
        for i, an in enumerate(annots):
            an.xy = (xy[i, 0], xy[i, 1])
        fig.canvas.draw_idle()

    def on_press(event):
        if event.inaxes is not ax or event.xdata is None:
            return
        d = np.hypot(xy[:, 0] - event.xdata, xy[:, 1] - event.ydata)
        i = int(np.argmin(d))
        if d[i] <= PICK_RADIUS_M:
            state["drag"] = i

    def on_motion(event):
        i = state["drag"]
        if i is None or event.inaxes is not ax or event.xdata is None:
            return
        xy[i] = (event.xdata, event.ydata)
        redraw()

    def on_release(event):
        i = state["drag"]
        if i is not None:
            print(f"SMS {labels[i]:>8}  ->  x={xy[i,0]:8.3f}  y={xy[i,1]:8.3f}")
        state["drag"] = None

    def on_key(event):
        if event.key == "s":
            save_csv(pairs, xy)
        elif event.key == "r":
            xy[:] = np.column_stack((x0, y0))
            redraw()
            print("reset to original positions")

    fig.canvas.mpl_connect("button_press_event", on_press)
    fig.canvas.mpl_connect("motion_notify_event", on_motion)
    fig.canvas.mpl_connect("button_release_event", on_release)
    fig.canvas.mpl_connect("key_press_event", on_key)

    print("drag markers; press 's' to save, 'r' to reset.")
    plt.show()


def save_csv(pairs, xy) -> None:
    """Write picked positions in canonical and raw frame."""
    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sensor_ids", "widmer_location", "treatment",
                    "x_canon", "y_canon", "X_raw", "Y_raw", "Z_av"])
        for p, (xc, yc) in zip(pairs, xy):
            xr, yr = to_canonical_xy(float(xc), float(yc))  # flip is self-inverse
            w.writerow(["|".join(p.sensor_ids), p.widmer_location or "",
                        p.treatment or "", f"{xc:.6f}", f"{yc:.6f}",
                        f"{xr:.6f}", f"{yr:.6f}", f"{p.z:.6f}"])
    print(f"wrote {OUT_CSV.relative_to(ROOT)}  ({len(pairs)} stations)")


if __name__ == "__main__":
    main()
