"""Apply per-scan rotation table and render aligned plan views.

Starts from the histograms computed by ``scripts/13_xyz_inventory.py``
(cached on disk via ``swale.xyz_align.compute_or_load_histogram``) and
applies a per-file ``(flip_ud, rot_cw_steps)`` transform from the
table in ``ROTATION_TABLE`` below. Outputs:

  * ``plots/14_xyz_aligned/<safe_name>.png`` — per-file plan view
    after the transform, with the Mesh_swale_site.vtk extent overlaid.
  * ``plots/14_xyz_aligned_coverage.png`` — all bounding boxes
    post-transform on one figure, helps see whether the scans now
    cluster in a common frame.

Re-run is cheap thanks to the disk cache: first invocation streams the
6.6 GB of source files (~3 min); subsequent ones with the same
``BINS_XY`` reuse cached histograms.

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/14_xyz_aligned.py
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv

from swale.xyz_align import (
    apply_transform,
    compute_or_load_histogram,
)

ROOT = Path(__file__).resolve().parent.parent
XYZ_DIR = ROOT / "data" / "DEM_xyz"
DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"
CACHE_DIR = ROOT / "cache" / "xyz_histograms"

OUT_DIR = ROOT / "plots" / "14_xyz_aligned"
OUT_COVERAGE = ROOT / "plots" / "14_xyz_aligned_coverage.png"

BINS_XY = (1000, 1000)
CMAP = "terrain"
MIN_POINTS_FOR_BIN = 2

# Reference scan (the orientation the user specified). All other scans
# start with the same transform until inspection suggests otherwise.
REFERENCE_FILENAME = "24.05.30_-_con_sw_and_for_2_12_44_34.xyz"

# Per-file (flip_ud, rot_cw_steps) transform. Add overrides as we
# inspect the rendered plots. The default falls back to the reference
# transform below.
#
# Composed transform: the raw scan is flipped vertically (mirror across
# horizontal axis). No additional rotation. After this, North = +Y.
# Earlier iterations added a 90° CW rotation, then a 90° CCW rotation
# to get North on the Y axis; the two rotations cancel, so the net
# is just the up-down flip.
ROTATION_TABLE: dict[str, tuple[bool, int]] = {
    # filename -> (flip_ud, rot_cw_steps)
    REFERENCE_FILENAME: (True, 0),
}
DEFAULT_TRANSFORM = (True, 0)


def transform_for(filename: str) -> tuple[bool, int]:
    return ROTATION_TABLE.get(filename, DEFAULT_TRANSFORM)


def get_dem_bbox() -> tuple[float, float, float, float] | None:
    if not DEM_MESH.exists():
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = pv.read(DEM_MESH)
    b = m.bounds
    return b.x_min, b.x_max, b.y_min, b.y_max


def render_aligned(
    filename: str,
    zsum: np.ndarray,
    count: np.ndarray,
    summary,
    flip_ud: bool,
    rot_cw_steps: int,
    dem_bbox: tuple[float, float, float, float] | None,
    out_png: Path,
) -> tuple[float, float, float, float]:
    """Render the transformed mean-Z grid; return the post-transform extent."""
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_z = np.where(
            count >= MIN_POINTS_FOR_BIN,
            zsum / np.maximum(count, 1),
            np.nan,
        )

    # Convert to display orientation (rows=y, cols=x) before transforming.
    image = mean_z.T
    extent = (summary.x_min, summary.x_max, summary.y_min, summary.y_max)
    image_t, extent_t = apply_transform(
        image, extent, flip_ud=flip_ud, rot_cw_steps=rot_cw_steps,
    )

    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(
        image_t,
        origin="lower", extent=extent_t,
        cmap=CMAP, interpolation="nearest", aspect="equal",
    )
    cbar = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Mean Z per bin (m)")

    if dem_bbox is not None:
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=1.5, alpha=0.7,
                label="Mesh_swale_site.vtk extent")
        ax.legend(loc="upper left", fontsize=8, frameon=True)

    ax.set_xlabel("X (m, aligned frame)")
    ax.set_ylabel("Y (m, aligned frame)")
    ax.set_title(
        f"{filename}\n"
        f"transform: flip_ud={flip_ud}, rot_cw_steps={rot_cw_steps}  |  "
        f"{summary.n_points:,} pts  Z[{summary.z_min:.2f}, {summary.z_max:.2f}] m",
        fontsize=9,
    )
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)
    return extent_t


def render_coverage(
    boxes: list[tuple[str, tuple[float, float, float, float], int]],
    dem_bbox: tuple[float, float, float, float] | None,
    out_png: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 11))
    colors = plt.cm.tab20(np.linspace(0, 1, max(len(boxes), 1)))
    for (name, ext, n), c in zip(boxes, colors):
        x0, x1, y0, y1 = ext
        ax.plot([x0, x1, x1, x0, x0],
                [y0, y0, y1, y1, y0],
                color=c, lw=1.4, alpha=0.85,
                label=f"{name}  (n={n/1e6:.1f}M)")
    if dem_bbox is not None:
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=2.5, ls="--", alpha=0.9,
                label="Mesh_swale_site.vtk extent")
    ax.set_xlabel("X (m, aligned frame)")
    ax.set_ylabel("Y (m, aligned frame)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_title(
        f"XY bounding boxes after the rotation table (n={len(boxes)} scans)\n"
        f"Files with aligned frames should overlap on the same area",
        fontsize=11,
    )
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
              fontsize=7, frameon=True, ncol=1)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(XYZ_DIR.glob("*.xyz"), key=lambda p: p.stat().st_size)
    if not files:
        raise FileNotFoundError(f"no .xyz files in {XYZ_DIR}")
    print(f"Processing {len(files)} files; cache dir = {CACHE_DIR.relative_to(ROOT)}")

    dem_bbox = get_dem_bbox()
    boxes: list[tuple[str, tuple[float, float, float, float], int]] = []

    for i, p in enumerate(files, 1):
        flip_ud, rot_cw_steps = transform_for(p.name)
        marker = "[REFERENCE]" if p.name == REFERENCE_FILENAME else ""
        print(f"\n[{i}/{len(files)}] {p.name}  "
              f"transform=(flip_ud={flip_ud}, rot_cw={rot_cw_steps})  {marker}")

        zsum, count, s = compute_or_load_histogram(
            p, CACHE_DIR, bins_xy=BINS_XY,
        )
        print(f"  {s.n_points:,} pts  "
              f"X[{s.x_min:.1f},{s.x_max:.1f}]  "
              f"Y[{s.y_min:.1f},{s.y_max:.1f}]  "
              f"Z[{s.z_min:.2f},{s.z_max:.2f}]")

        from re import sub as _resub
        safe = _resub(r"[^A-Za-z0-9._-]+", "_", Path(p.name).stem)
        out_png = OUT_DIR / f"{safe}.png"
        ext_t = render_aligned(
            p.name, zsum, count, s,
            flip_ud=flip_ud, rot_cw_steps=rot_cw_steps,
            dem_bbox=dem_bbox, out_png=out_png,
        )
        print(f"  wrote {out_png.relative_to(ROOT)}  "
              f"X'[{ext_t[0]:.1f},{ext_t[1]:.1f}] Y'[{ext_t[2]:.1f},{ext_t[3]:.1f}]")
        boxes.append((p.name, ext_t, s.n_points))

    render_coverage(boxes, dem_bbox, OUT_COVERAGE)
    print(f"\nWrote {OUT_COVERAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
