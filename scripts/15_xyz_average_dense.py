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

from swale.xyz_align import apply_transform, compute_or_load_histogram

ROOT = Path(__file__).resolve().parent.parent
XYZ_DIR = ROOT / "data" / "DEM_xyz"
DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"
CACHE_DIR = ROOT / "cache" / "xyz_histograms"

OUT_AVG = ROOT / "plots" / "15_xyz_averaged.png"
OUT_STD = ROOT / "plots" / "15_xyz_stddev_per_bin.png"
OUT_COMPARE = ROOT / "plots" / "15_xyz_average_vs_single.png"

BINS_XY = (1000, 1000)
# Net transform: vertical flip only (North = +Y after the flip).
# Earlier we composed flip + CW 90 + CCW 90; the two rotations cancel.
TRANSFORM = {"flip_ud": True, "rot_cw_steps": 0}
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
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = pv.read(DEM_MESH)
    b = m.bounds
    return b.x_min, b.x_max, b.y_min, b.y_max


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
    ax.set_xlabel("X (m, aligned frame)")
    ax.set_ylabel("Y (m, aligned frame)")
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
        ax.set_xlabel("X (m, aligned)")
        ax.set_ylabel("Y (m, aligned)")
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
    plot_field(
        avg_mean, extent,
        f"Average of {len(DENSE_FILES)} dense con_sw_and_for_* scans\n"
        f"Combined {int(avg_count.sum()):,} points across "
        f"{int((avg_count >= MIN_POINTS_FOR_BIN).sum()):,} filled bins  "
        f"({100.0 * (avg_count >= MIN_POINTS_FOR_BIN).sum() / avg_count.size:.1f}%)",
        "Mean Z per bin (m)", CMAP_Z, OUT_AVG, dem_bbox,
    )
    print(f"  wrote {OUT_AVG.relative_to(ROOT)}")

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
