"""Average the 5 dense con_sw_and_for_*.xyz scans for noise reduction.

The 5 dense scans share identical point counts (28,541,143), identical
bounding boxes, and the same scanner frame (verified via permutation-
invariant moments). They were 5 independent measurements of the same
area, so averaging them reduces the per-bin Z noise by ~sqrt(5).

Outputs:

  * ``plots/15_xyz_averaged.png`` — combined mean-Z plan view after the
    rotation table's ``(flip_ud=True, rot_cw_steps=1)`` transform.
  * ``plots/15_xyz_stddev_per_bin.png`` — per-bin standard deviation of
    the 5 scan means, in the aligned frame. Bright = scans disagree.
  * ``plots/15_xyz_average_vs_single.png`` — side-by-side comparison
    (single scan vs 5-scan average) to show the noise reduction.

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/15_xyz_average_dense.py
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv

from swale.spatial_frame import (
    load_canonical_dem_mesh,
    xyz_rotation_table_default,
)
from swale.xyz_align import apply_transform, compute_or_load_histogram

ROOT = Path(__file__).resolve().parent.parent
XYZ_DIR = ROOT / "data" / "DEM_xyz"
DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"
CACHE_DIR = ROOT / "cache" / "xyz_histograms"

OUT_AVG = ROOT / "plots" / "15_xyz_averaged.png"
OUT_STD = ROOT / "plots" / "15_xyz_stddev_per_bin.png"
OUT_COMPARE = ROOT / "plots" / "15_xyz_average_vs_single.png"
OUT_DEM_TXT = ROOT / "data" / "DEM" / "DEM_xyz_average_dense_canonical.txt"
OUT_DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site_from_xyz_average.vtk"

BINS_XY = (1000, 1000)
# Net transform to reach the canonical frame (+X=East, +Y=North):
# flip vertically (aligns raw scan with raw DEM frame), then rotate
# 180 degrees (raw DEM -> canonical). See swale.spatial_frame.
_FLIP_UD, _ROT_CW = xyz_rotation_table_default()
TRANSFORM = {"flip_ud": _FLIP_UD, "rot_cw_steps": _ROT_CW}
MIN_POINTS_FOR_BIN = 2
CMAP_Z = "terrain"
CMAP_STD = "viridis"

# The 5 dense con_sw_and_for scans (28.5M points each, same frame).
DENSE_FILES = [
    "24.05.30_-_con_sw_and_for_2_13_23_43.xyz",
    "24.05.30_-_con_sw_and_for_3_11_56_35.xyz",
    "24.05.30_-_con_sw_and_for_3_12_16_16.xyz",
    "24.05.30_-_con_sw_and_for_11_24_35.xyz",
    "24.05.30_-_con_sw_and_for_11_59_00.xyz",
]


def get_dem_bbox() -> tuple[float, float, float, float] | None:
    if not DEM_MESH.exists():
        return None
    m = load_canonical_dem_mesh(DEM_MESH)
    x_min, x_max, y_min, y_max, _, _ = m.bounds
    return x_min, x_max, y_min, y_max


def crop_to_bbox(
    image: np.ndarray,
    extent: tuple[float, float, float, float],
    bbox: tuple[float, float, float, float],
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Crop an imshow-style image to a bounding box, snapping to grid edges."""
    x0, x1, y0, y1 = extent
    bx0, bx1, by0, by1 = bbox
    ny, nx = image.shape
    dx = (x1 - x0) / nx
    dy = (y1 - y0) / ny

    bx0_c = max(bx0, x0)
    bx1_c = min(bx1, x1)
    by0_c = max(by0, y0)
    by1_c = min(by1, y1)

    i0 = max(int(np.floor((bx0_c - x0) / dx)), 0)
    i1 = min(int(np.ceil((bx1_c - x0) / dx)), nx)
    j0 = max(int(np.floor((by0_c - y0) / dy)), 0)
    j1 = min(int(np.ceil((by1_c - y0) / dy)), ny)

    if i1 <= i0 or j1 <= j0:
        raise RuntimeError(
            f"crop produced empty image: extent={extent} bbox={bbox}"
        )

    cropped = image[j0:j1, i0:i1]
    extent_c = (x0 + i0 * dx, x0 + i1 * dx, y0 + j0 * dy, y0 + j1 * dy)
    return cropped, extent_c


def canonical_average_grid(
    mean_z: np.ndarray,
    extent: tuple[float, float, float, float],
    dem_bbox: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Return the averaged grid in canonical orientation, cropped to site bbox."""
    image, extent_t = apply_transform(mean_z.T, extent, **TRANSFORM)
    if dem_bbox is not None:
        image, extent_t = crop_to_bbox(image, extent_t, dem_bbox)
    return image, extent_t


def export_dem_text(
    image: np.ndarray,
    extent: tuple[float, float, float, float],
    out_path: Path,
) -> int:
    """Write the canonical averaged DEM grid as XYZ text."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ny, nx = image.shape
    x0, x1, y0, y1 = extent
    xs = np.linspace(x0, x1, nx, endpoint=False) + 0.5 * (x1 - x0) / nx
    ys = np.linspace(y0, y1, ny, endpoint=False) + 0.5 * (y1 - y0) / ny
    xx, yy = np.meshgrid(xs, ys)
    mask = np.isfinite(image)
    xyz = np.column_stack((xx[mask], yy[mask], image[mask]))
    header = "X Y Z\n# Canonical frame: +X=East, +Y=North, +Z=up"
    np.savetxt(out_path, xyz, fmt="%.6f", header=header, comments="# ")
    return int(xyz.shape[0])


def export_dem_mesh(
    image: np.ndarray,
    extent: tuple[float, float, float, float],
    out_path: Path,
) -> tuple[int, int]:
    """Write the canonical averaged DEM grid as a triangulated VTK mesh."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ny, nx = image.shape
    x0, x1, y0, y1 = extent
    xs = np.linspace(x0, x1, nx, endpoint=False) + 0.5 * (x1 - x0) / nx
    ys = np.linspace(y0, y1, ny, endpoint=False) + 0.5 * (y1 - y0) / ny
    xx, yy = np.meshgrid(xs, ys)

    grid = pv.StructuredGrid(xx, yy, image)
    surface = grid.extract_surface().triangulate()

    finite_cells = np.ones(surface.n_cells, dtype=bool)
    faces = surface.faces.reshape(-1, 4)
    for cell_idx, (_, a, b, c) in enumerate(faces):
        if not np.all(np.isfinite(surface.points[[a, b, c], 2])):
            finite_cells[cell_idx] = False
    mesh = (
        surface.extract_cells(np.flatnonzero(finite_cells))
        .extract_surface()
        .triangulate()
    )
    mesh.save(out_path)
    return int(mesh.n_points), int(mesh.n_cells)


def load_all() -> tuple[list[np.ndarray], list[np.ndarray], tuple]:
    """Load all 5 histograms; return (zsums, counts, common_extent)."""
    zsums, counts, extents = [], [], []
    for name in DENSE_FILES:
        zsum, count, summary = compute_or_load_histogram(
            XYZ_DIR / name, CACHE_DIR, bins_xy=BINS_XY,
        )
        zsums.append(zsum)
        counts.append(count)
        extents.append((summary.x_min, summary.x_max,
                         summary.y_min, summary.y_max))
    # Sanity check: all 5 should share the same extent
    if not all(e == extents[0] for e in extents):
        warnings.warn(
            f"5 scans do not share identical extents; using ref's. extents={extents}"
        )
    return zsums, counts, extents[0]


def combine_average(zsums: list[np.ndarray],
                     counts: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Per-bin combined mean Z and combined count across all 5 scans."""
    total_zsum = sum(zsums)
    total_count = sum(counts)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_z = np.where(
            total_count >= MIN_POINTS_FOR_BIN,
            total_zsum / np.maximum(total_count, 1),
            np.nan,
        )
    return mean_z, total_count


def per_bin_stddev(zsums: list[np.ndarray],
                    counts: list[np.ndarray]) -> np.ndarray:
    """Standard deviation of the 5 per-scan mean-Z values per bin.

    For each (i, j) bin where all 5 scans have at least one point, take
    the 5 individual mean-Z values and report their std. Bins where any
    scan is empty are flagged with NaN.
    """
    means = []
    masks = []
    for z, c in zip(zsums, counts):
        with np.errstate(invalid="ignore", divide="ignore"):
            m = np.where(c >= MIN_POINTS_FOR_BIN, z / np.maximum(c, 1), np.nan)
        means.append(m)
        masks.append(c >= MIN_POINTS_FOR_BIN)
    stack = np.stack(means, axis=0)             # (5, nx, ny)
    all_filled = np.stack(masks, axis=0).all(axis=0)
    std = np.nanstd(stack, axis=0, ddof=1)
    return np.where(all_filled, std, np.nan)


def plot_field(arr: np.ndarray,
                extent: tuple,
                title: str,
                cbar_label: str,
                cmap: str,
                out_png: Path,
                dem_bbox: tuple | None) -> None:
    """Apply rotation + render a single 2-D field."""
    image, ext_t = apply_transform(arr.T, extent, **TRANSFORM)
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(image, origin="lower", extent=ext_t,
                    cmap=cmap, interpolation="nearest", aspect="equal")
    cbar = fig.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label(cbar_label)
    if dem_bbox is not None:
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=1.5, alpha=0.7,
                label="Mesh_swale_site.vtk extent")
        ax.legend(loc="upper left", fontsize=8, frameon=True)
    ax.set_xlabel("X (m, canonical frame; +X = East)")
    ax.set_ylabel("Y (m, canonical frame; +Y = North)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.2)
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def plot_average_vs_single(
    single_zsum: np.ndarray, single_count: np.ndarray,
    avg_mean: np.ndarray, avg_count: np.ndarray,
    extent: tuple, out_png: Path, dem_bbox: tuple | None,
) -> None:
    """Side-by-side: a single scan's mean-Z next to the 5-scan average."""
    with np.errstate(invalid="ignore", divide="ignore"):
        single_mean = np.where(
            single_count >= MIN_POINTS_FOR_BIN,
            single_zsum / np.maximum(single_count, 1),
            np.nan,
        )

    img_single, ext_t = apply_transform(single_mean.T, extent, **TRANSFORM)
    img_avg, _ = apply_transform(avg_mean.T, extent, **TRANSFORM)

    # Shared colour scale for fair comparison.
    vmin = np.nanmin([np.nanmin(img_single), np.nanmin(img_avg)])
    vmax = np.nanmax([np.nanmax(img_single), np.nanmax(img_avg)])

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    for ax, img, title in (
        (axes[0], img_single, "Single scan (e.g., _11_59_00.xyz)"),
        (axes[1], img_avg,    "Average of 5 dense scans"),
    ):
        im = ax.imshow(img, origin="lower", extent=ext_t,
                        cmap=CMAP_Z, interpolation="nearest", aspect="equal",
                        vmin=vmin, vmax=vmax)
        ax.set_xlabel("X (m, canonical; +X = East)")
        ax.set_ylabel("Y (m, canonical; +Y = North)")
        ax.set_title(title, fontsize=11)
        ax.grid(alpha=0.2)
        if dem_bbox is not None:
            bx0, bx1, by0, by1 = dem_bbox
            ax.plot([bx0, bx1, bx1, bx0, bx0],
                    [by0, by0, by1, by1, by0],
                    color="red", lw=1.0, alpha=0.6)
    cbar = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02)
    cbar.set_label("Mean Z per bin (m)")
    fig.suptitle("Single scan vs 5-scan average (same colour scale)",
                  fontsize=12, weight="bold")
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def main() -> None:
    OUT_AVG.parent.mkdir(exist_ok=True)
    dem_bbox = get_dem_bbox()

    print(f"Loading {len(DENSE_FILES)} dense scan histograms from cache ...")
    zsums, counts, extent = load_all()
    print(f"  shared extent: X[{extent[0]:.1f},{extent[1]:.1f}]  "
          f"Y[{extent[2]:.1f},{extent[3]:.1f}]")

    print("Computing 5-scan mean-Z grid ...")
    avg_mean, avg_count = combine_average(zsums, counts)
    canonical_avg, canonical_extent = canonical_average_grid(
        avg_mean, extent, dem_bbox
    )
    plot_field(
        avg_mean, extent,
        f"Average of {len(DENSE_FILES)} dense con_sw_and_for_* scans\n"
        f"Combined {int(avg_count.sum()):,} points across "
        f"{int((avg_count >= MIN_POINTS_FOR_BIN).sum()):,} filled bins  "
        f"({100.0 * (avg_count >= MIN_POINTS_FOR_BIN).sum() / avg_count.size:.1f}%)",
        "Mean Z per bin (m)", CMAP_Z, OUT_AVG, dem_bbox,
    )
    print(f"  wrote {OUT_AVG.relative_to(ROOT)}")

    print("Exporting averaged DEM artifacts ...")
    n_xyz = export_dem_text(canonical_avg, canonical_extent, OUT_DEM_TXT)
    n_pts, n_tri = export_dem_mesh(
        canonical_avg, canonical_extent, OUT_DEM_MESH
    )
    print(f"  wrote {OUT_DEM_TXT.relative_to(ROOT)}  ({n_xyz:,} xyz rows)")
    print(
        f"  wrote {OUT_DEM_MESH.relative_to(ROOT)}  "
        f"({n_pts:,} points, {n_tri:,} triangles)"
    )

    print("Computing per-bin std (5-scan disagreement map) ...")
    std = per_bin_stddev(zsums, counts)
    n_all_filled = int(np.isfinite(std).sum())
    print(f"  {n_all_filled:,} bins have data from all 5 scans  "
          f"(median std = {float(np.nanmedian(std))*100:.1f} cm)")
    plot_field(
        std, extent,
        f"Per-bin std of mean-Z across 5 scans\n"
        f"Bright = scans disagree (registration error / vegetation / scanner edge)",
        "Std Z per bin (m)", CMAP_STD, OUT_STD, dem_bbox,
    )
    print(f"  wrote {OUT_STD.relative_to(ROOT)}")

    print("Single vs average side-by-side ...")
    plot_average_vs_single(
        zsums[-1], counts[-1],
        avg_mean, avg_count,
        extent, OUT_COMPARE, dem_bbox,
    )
    print(f"  wrote {OUT_COMPARE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
