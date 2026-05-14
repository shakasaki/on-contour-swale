"""Hillshade base layer for canonical-frame map plots.

The 5 dense ``con_sw_and_for_*.xyz`` scans, averaged and projected to
the canonical frame (+X=East, +Y=North), are the highest-resolution
surface model we have for the swale site (10^7 points; ~1 mm per-bin
std across scans). This module exposes one helper,
:func:`load_canonical_hillshade`, that returns a grayscale hillshade
image cropped to the cleaned DEM mesh extent — ready to drop in as a
base layer under any plan-view scatter (sensor markers, recession-τ
maps, etc.).

The averaging follows the same logic as
``scripts/15_xyz_average_dense.py`` (combined mean over the 5 cached
histograms), and the transform follows
:func:`swale.spatial_frame.xyz_rotation_table_default`, so the output
is in the exact same frame as every other map plot in the project.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np

from swale.spatial_frame import (
    load_canonical_dem_mesh,
    xyz_rotation_table_default,
)
from swale.xyz_align import apply_transform, compute_or_load_histogram

# The 5 dense scans averaged for the hillshade. Same list as
# scripts/15_xyz_average_dense.py — keep in sync if scans change.
_DENSE_FILES: tuple[str, ...] = (
    "24.05.30_-_con_sw_and_for_2_13_23_43.xyz",
    "24.05.30_-_con_sw_and_for_3_11_56_35.xyz",
    "24.05.30_-_con_sw_and_for_3_12_16_16.xyz",
    "24.05.30_-_con_sw_and_for_11_24_35.xyz",
    "24.05.30_-_con_sw_and_for_11_59_00.xyz",
)

_DEFAULT_BINS_XY: tuple[int, int] = (1000, 1000)
_MIN_POINTS_FOR_BIN = 2


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _averaged_mean_z(
    xyz_dir: Path,
    cache_dir: Path,
    bins_xy: tuple[int, int],
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Combined mean-Z over the 5 dense scans + their shared raw extent."""
    zsums, counts, extents = [], [], []
    for name in _DENSE_FILES:
        zsum, count, summary = compute_or_load_histogram(
            xyz_dir / name, cache_dir, bins_xy=bins_xy,
        )
        zsums.append(zsum)
        counts.append(count)
        extents.append((summary.x_min, summary.x_max,
                         summary.y_min, summary.y_max))
    total_zsum = sum(zsums)
    total_count = sum(counts)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_z = np.where(
            total_count >= _MIN_POINTS_FOR_BIN,
            total_zsum / np.maximum(total_count, 1),
            np.nan,
        )
    # Histograms share extent to within sub-cm; take the first.
    return mean_z, extents[0]


def _crop_to_bbox(
    image: np.ndarray,
    extent: tuple[float, float, float, float],
    bbox: tuple[float, float, float, float],
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Crop an imshow-style 2-D image (rows=y, cols=x) to a sub-bbox.

    Both ``extent`` and ``bbox`` are ``(x_min, x_max, y_min, y_max)``
    in the same coordinate frame. The returned extent reflects the
    actual pixel boundaries (which align to the source grid; the
    requested bbox is snapped outward to the nearest cell edge).
    """
    x0, x1, y0, y1 = extent
    bx0, bx1, by0, by1 = bbox
    ny, nx = image.shape
    dx = (x1 - x0) / nx
    dy = (y1 - y0) / ny

    bx0_c = max(bx0, x0); bx1_c = min(bx1, x1)
    by0_c = max(by0, y0); by1_c = min(by1, y1)

    i0 = max(int(np.floor((bx0_c - x0) / dx)), 0)
    i1 = min(int(np.ceil((bx1_c - x0) / dx)), nx)
    j0 = max(int(np.floor((by0_c - y0) / dy)), 0)
    j1 = min(int(np.ceil((by1_c - y0) / dy)), ny)

    if i1 <= i0 or j1 <= j0:
        raise RuntimeError(
            f"crop produced empty image: extent={extent} bbox={bbox}"
        )
    cropped = image[j0:j1, i0:i1]
    extent_c = (x0 + i0 * dx, x0 + i1 * dx,
                y0 + j0 * dy, y0 + j1 * dy)
    return cropped, extent_c


def load_canonical_hillshade(
    *,
    xyz_dir: Path | None = None,
    cache_dir: Path | None = None,
    dem_mesh_path: Path | None = None,
    bins_xy: tuple[int, int] = _DEFAULT_BINS_XY,
    azdeg: float = 315.0,
    altdeg: float = 45.0,
    vert_exag: float = 5.0,
    crop_to_dem_mesh: bool = True,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Return a canonical-frame hillshade image + its imshow extent.

    Pipeline:
      1. Load the 5 dense ``con_sw_and_for_*`` scan histograms from
         ``cache/xyz_histograms``.
      2. Combine into one mean-Z grid (same as 15_xyz_average_dense).
      3. Apply the canonical-frame transform (flip_ud + 180-degree
         rotation, per :func:`swale.spatial_frame.xyz_rotation_table_default`).
      4. Crop to the DEM mesh extent if ``crop_to_dem_mesh`` is True.
      5. Compute a luminance hillshade via
         :class:`matplotlib.colors.LightSource` with the given azimuth,
         altitude, and vertical exaggeration.

    Args:
        xyz_dir: Directory holding the raw ``.xyz`` files. Defaults to
            ``<repo>/data/DEM_xyz``.
        cache_dir: Directory holding the cached histograms. Defaults to
            ``<repo>/cache/xyz_histograms``.
        dem_mesh_path: VTK mesh used to compute the crop bbox. Defaults
            to ``<repo>/data/DEM/Mesh_swale_site.vtk``.
        bins_xy: Histogram grid resolution (must match the cache).
        azdeg, altdeg: Solar illumination, NW + 45 degrees by default.
        vert_exag: Vertical exaggeration for hillshade contrast. The
            site has ~3 m of relief over ~30 m, so a 5x exaggeration
            keeps the swale/mound features visible without blowing out.
        crop_to_dem_mesh: If True (default), crop the averaged grid to
            the DEM mesh bbox so the hillshade only covers the cleaned
            survey area.

    Returns:
        ``(hillshade, extent)`` where ``hillshade`` is a 2-D float
        array in [0, 1] (NaN where the averaged grid had no data) and
        ``extent`` is ``(x_min, x_max, y_min, y_max)`` ready for
        ``ax.imshow(..., origin='lower', extent=extent)``.
    """
    repo_root = _repo_root()
    xyz_dir = xyz_dir or (repo_root / "data" / "DEM_xyz")
    cache_dir = cache_dir or (repo_root / "cache" / "xyz_histograms")
    dem_mesh_path = dem_mesh_path or (repo_root / "data" / "DEM"
                                       / "Mesh_swale_site.vtk")

    mean_z, raw_extent = _averaged_mean_z(xyz_dir, cache_dir, bins_xy)

    flip_ud, rot_cw = xyz_rotation_table_default()
    image, extent = apply_transform(
        mean_z.T, raw_extent,
        flip_ud=flip_ud, rot_cw_steps=rot_cw,
    )

    if crop_to_dem_mesh:
        mesh = load_canonical_dem_mesh(dem_mesh_path)
        b = mesh.bounds
        image, extent = _crop_to_bbox(
            image, extent, (b.x_min, b.x_max, b.y_min, b.y_max),
        )

    # Fill NaN with the in-cell mean before hillshade compute (LightSource
    # propagates NaN aggressively); restore NaN mask on the output.
    finite = np.isfinite(image)
    if not finite.any():
        raise RuntimeError("averaged grid is all NaN after cropping")
    filled = np.where(finite, image, float(np.nanmean(image)))

    x0, x1, y0, y1 = extent
    dx = (x1 - x0) / image.shape[1]
    dy = (y1 - y0) / image.shape[0]

    ls = mcolors.LightSource(azdeg=azdeg, altdeg=altdeg)
    hs = ls.hillshade(filled, vert_exag=vert_exag, dx=dx, dy=dy)
    hs = np.where(finite, hs, np.nan)
    return hs, extent
