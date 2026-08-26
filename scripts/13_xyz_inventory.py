"""Inventory and 2-D maps of the raw .xyz scans under ``data/DEM_xyz/``.

For each ``.xyz`` file: stream-scan to learn point count + XYZ extents,
then stream-accumulate a 2-D mean-Z grid over the XY plane. Outputs:

  * ``plots/13_xyz_inventory.csv`` — per-file row: filename, point
    count, XY/Z extents, file size, processing time.
  * ``plots/13_xyz/<safe_name>.png`` — per-file plan view (mean Z),
    overlaid with the cleaned ``Mesh_swale_site.vtk`` bounding box for
    quick context.
  * ``plots/13_xyz_coverage.png`` — combined view: every file's XY
    bounding box on one axis, colour-coded; helps tell which files
    share a frame.

Memory bounded by ``BINS_XY`` (default 1000×1000). Two passes per file:
first for extents, second for the histogram. Tune ``BINS_XY`` /
``CHUNK_LINES`` at the top of the script.

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/13_xyz_inventory.py
"""

from __future__ import annotations

import csv
import re
import time
import warnings
from dataclasses import asdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv

from swale.xyz_streaming import (
    XYZSummary,
    histogram2d_xyz,
    summarize_xyz,
)

ROOT = Path(__file__).resolve().parent.parent
XYZ_DIR = ROOT / "data" / "DEM_xyz"
DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"

OUT_INVENTORY_CSV = ROOT / "plots" / "13_xyz_inventory.csv"
OUT_PER_FILE_DIR = ROOT / "plots" / "13_xyz"
OUT_COVERAGE_PNG = ROOT / "plots" / "13_xyz_coverage.png"

# Tunables
BINS_XY = (1000, 1000)               # 1e6 cells; ≈ 16 MB for zsum+count
CHUNK_LINES = 200_000                # ≈ 9.6 MB of float64 per chunk
CMAP = "terrain"
MIN_POINTS_FOR_BIN = 2               # bins with fewer points than this -> NaN


def safe_filename(name: str) -> str:
    """Filesystem-friendly stem for output PNGs."""
    stem = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem)


def get_dem_bbox() -> tuple[float, float, float, float]:
    """XY bounding box of the cleaned site mesh, for overlay context."""
    if not DEM_MESH.exists():
        return float("nan"), float("nan"), float("nan"), float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = pv.read(DEM_MESH)
    b = m.bounds
    return b.x_min, b.x_max, b.y_min, b.y_max


def render_one(summary: XYZSummary,
                zsum: np.ndarray, count: np.ndarray,
                dem_bbox: tuple[float, float, float, float],
                out_png: Path) -> None:
    """Render a single .xyz file's mean-Z grid as a PNG."""
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_z = np.where(count >= MIN_POINTS_FOR_BIN, zsum / np.maximum(count, 1), np.nan)

    fig, ax = plt.subplots(figsize=(9, 8))
    extent = (summary.x_min, summary.x_max, summary.y_min, summary.y_max)
    # mean_z is indexed (ix, iy) -> transpose to (iy, ix) for imshow
    im = ax.imshow(
        mean_z.T,
        origin="lower", extent=extent,
        cmap=CMAP, interpolation="nearest", aspect="equal",
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Mean Z per bin (m)")

    # Overlay the cleaned DEM bounding box for spatial context (if it
    # falls inside the scan's extent).
    if all(np.isfinite(v) for v in dem_bbox):
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=1.5, alpha=0.7,
                label="Mesh_swale_site.vtk extent")
        ax.legend(loc="upper left", fontsize=8, frameon=True)

    n_filled = int((count >= MIN_POINTS_FOR_BIN).sum())
    coverage_pct = 100.0 * n_filled / count.size
    ax.set_xlabel("X (m, raw scan frame)")
    ax.set_ylabel("Y (m, raw scan frame)")
    ax.set_title(
        f"{summary.path.name}\n"
        f"{summary.n_points:,} points  "
        f"X [{summary.x_min:.1f}, {summary.x_max:.1f}]  "
        f"Y [{summary.y_min:.1f}, {summary.y_max:.1f}]  "
        f"Z [{summary.z_min:.2f}, {summary.z_max:.2f}]  "
        f"({summary.file_size_bytes/1e6:.0f} MB; {coverage_pct:.1f}% bins filled)",
        fontsize=9,
    )
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def render_coverage(summaries: list[XYZSummary],
                     dem_bbox: tuple[float, float, float, float],
                     out_png: Path) -> None:
    """One combined plot showing every file's XY bounding box."""
    fig, ax = plt.subplots(figsize=(12, 11))

    colors = plt.cm.tab20(np.linspace(0, 1, max(len(summaries), 1)))
    for s, c in zip(summaries, colors):
        rect_x = [s.x_min, s.x_max, s.x_max, s.x_min, s.x_min]
        rect_y = [s.y_min, s.y_min, s.y_max, s.y_max, s.y_min]
        ax.plot(rect_x, rect_y, color=c, lw=1.4, alpha=0.85,
                label=f"{s.path.name}  (n={s.n_points/1e6:.1f}M)")

    if all(np.isfinite(v) for v in dem_bbox):
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=2.5, ls="--", alpha=0.9,
                label="Mesh_swale_site.vtk extent (red)")

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_title(
        f"XY bounding boxes of {len(summaries)} raw .xyz scans + DEM mesh extent\n"
        f"Files sharing a frame should cluster together; distinct frames separate",
        fontsize=11,
    )
    # Legend off to the side
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
              fontsize=7, frameon=True, ncol=1)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not XYZ_DIR.exists():
        raise FileNotFoundError(XYZ_DIR)

    OUT_PER_FILE_DIR.mkdir(exist_ok=True)
    files = sorted(XYZ_DIR.glob("*.xyz"), key=lambda p: p.stat().st_size)
    print(f"Found {len(files)} .xyz files; total "
          f"{sum(p.stat().st_size for p in files)/1e9:.1f} GB.")

    dem_bbox = get_dem_bbox()

    summaries: list[XYZSummary] = []
    rows: list[dict] = []

    for i, p in enumerate(files, 1):
        size_mb = p.stat().st_size / 1e6
        print(f"\n[{i}/{len(files)}] {p.name}  ({size_mb:.0f} MB)")

        t0 = time.time()
        s = summarize_xyz(p, chunk_lines=CHUNK_LINES)
        t_summary = time.time() - t0
        print(f"  pass 1: {s.n_points:,} pts  "
              f"X[{s.x_min:.1f},{s.x_max:.1f}]  "
              f"Y[{s.y_min:.1f},{s.y_max:.1f}]  "
              f"Z[{s.z_min:.2f},{s.z_max:.2f}]  ({t_summary:.1f}s)")

        if s.n_points == 0:
            print(f"  SKIP — parser returned 0 points (unsupported format?)")
            rows.append({
                "filename":      p.name,
                "file_size_MB":  round(size_mb, 1),
                "n_points":      0,
                "x_min": "", "x_max": "", "y_min": "", "y_max": "",
                "z_min": "", "z_max": "",
                "t_summary_s":   round(t_summary, 1),
                "t_histogram_s": "",
                "plot_path":     "",
            })
            continue

        summaries.append(s)

        t0 = time.time()
        zsum, count = histogram2d_xyz(p, s, bins_xy=BINS_XY, chunk_lines=CHUNK_LINES)
        t_hist = time.time() - t0

        out_png = OUT_PER_FILE_DIR / f"{safe_filename(p.name)}.png"
        render_one(s, zsum, count, dem_bbox, out_png)
        print(f"  pass 2 + plot: wrote {out_png.relative_to(ROOT)}  ({t_hist:.1f}s)")

        rows.append({
            "filename":       p.name,
            "file_size_MB":   round(size_mb, 1),
            "n_points":       s.n_points,
            "x_min":          round(s.x_min, 3),
            "x_max":          round(s.x_max, 3),
            "y_min":          round(s.y_min, 3),
            "y_max":          round(s.y_max, 3),
            "z_min":          round(s.z_min, 3),
            "z_max":          round(s.z_max, 3),
            "t_summary_s":    round(t_summary, 1),
            "t_histogram_s":  round(t_hist, 1),
            "plot_path":      str(out_png.relative_to(ROOT)),
        })

    # Combined coverage view + inventory CSV
    render_coverage(summaries, dem_bbox, OUT_COVERAGE_PNG)
    print(f"\nWrote {OUT_COVERAGE_PNG.relative_to(ROOT)}")

    OUT_INVENTORY_CSV.parent.mkdir(exist_ok=True)
    with OUT_INVENTORY_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT_INVENTORY_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
