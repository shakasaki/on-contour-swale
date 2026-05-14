"""Histogram caching + dihedral-group transforms for XYZ scan plots.

Two helpers:

* :func:`compute_or_load_histogram` — wraps the two-pass streaming from
  :mod:`swale.xyz_streaming`, caching the resulting ``(zsum, count,
  summary)`` to ``cache/xyz_histograms/<safe>.npz`` so iterating on
  rotations / styling doesn't re-stream the multi-GB source files.

* :func:`apply_transform` — applies a ``(flip_ud, rot_cw_steps)``
  transform in display space and returns ``(image, extent)`` for
  ``imshow``. The transform composes a vertical flip with any number of
  90 degree CW rotations, covering all 8 symmetries of the dihedral
  group D4 (the rotation table per scan).
"""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

import numpy as np

from swale.xyz_streaming import (
    DEFAULT_CHUNK_LINES,
    XYZSummary,
    histogram2d_xyz,
    summarize_xyz,
)


def _safe_stem(name: str) -> str:
    """Filesystem-friendly stem for cache filenames."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)


def compute_or_load_histogram(
    path: Path,
    cache_dir: Path,
    *,
    bins_xy: tuple[int, int] = (1000, 1000),
    chunk_lines: int = DEFAULT_CHUNK_LINES,
    refresh: bool = False,
) -> tuple[np.ndarray, np.ndarray, XYZSummary]:
    """Return ``(zsum, count, summary)`` for ``path``, caching to ``cache_dir``.

    The cache key is the basename + ``bins_xy``. If the cache file exists
    and ``refresh`` is False, returns the cached arrays directly. The
    cache is invalidated implicitly when ``bins_xy`` changes (since the
    array shape would differ).

    Args:
        path: Source ``.xyz`` file.
        cache_dir: Directory to read/write cached histograms.
        bins_xy: Grid resolution as ``(nx, ny)``.
        chunk_lines: Lines per parsed chunk during streaming.
        refresh: Force recomputation even if a cache file exists.

    Returns:
        ``(zsum, count, summary)``. ``zsum`` and ``count`` both have
        shape ``bins_xy``; ``summary`` carries the original XYZ extents.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    nx, ny = bins_xy
    cache_path = cache_dir / f"{_safe_stem(path.name)}__{nx}x{ny}.npz"

    if cache_path.exists() and not refresh:
        z = np.load(cache_path, allow_pickle=False)
        if z["zsum"].shape == bins_xy:
            summary = XYZSummary(
                path=path,
                n_points=int(z["n_points"]),
                x_min=float(z["x_min"]), x_max=float(z["x_max"]),
                y_min=float(z["y_min"]), y_max=float(z["y_max"]),
                z_min=float(z["z_min"]), z_max=float(z["z_max"]),
                file_size_bytes=int(z["file_size_bytes"]),
            )
            return z["zsum"], z["count"], summary

    summary = summarize_xyz(path, chunk_lines=chunk_lines)
    if summary.n_points == 0:
        raise RuntimeError(f"no points parsed from {path}")
    zsum, count = histogram2d_xyz(path, summary,
                                    bins_xy=bins_xy, chunk_lines=chunk_lines)
    np.savez_compressed(
        cache_path,
        zsum=zsum, count=count,
        n_points=summary.n_points,
        x_min=summary.x_min, x_max=summary.x_max,
        y_min=summary.y_min, y_max=summary.y_max,
        z_min=summary.z_min, z_max=summary.z_max,
        file_size_bytes=summary.file_size_bytes,
    )
    return zsum, count, summary


def apply_transform(
    image: np.ndarray,
    extent: tuple[float, float, float, float],
    *,
    flip_ud: bool = False,
    rot_cw_steps: int = 0,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Apply a flip-UD + N×90° CW transform in display space.

    The transform composes (in this order):
      1. optional vertical flip (``np.flipud``)
      2. ``rot_cw_steps`` clockwise rotations of 90 degrees each.

    Both ``image`` and ``extent`` are updated consistently so that the
    transformed image stays a faithful plan view: pixel ``(i, j)`` of
    the result represents the same physical location as the original
    pixel under the composed transformation.

    Args:
        image: 2-D array oriented as it would be passed to ``imshow``
            with ``origin="lower"`` (rows = Y, cols = X).
        extent: Original ``(x_min, x_max, y_min, y_max)`` for ``image``.
        flip_ud: If True, flip vertically (mirror across horizontal axis)
            before rotating.
        rot_cw_steps: Number of 90 degree CW rotations to apply after
            the flip. Reduced mod 4.

    Returns:
        ``(image_new, extent_new)`` ready for ``imshow``.
    """
    out = np.asarray(image)
    x0, x1, y0, y1 = extent

    if flip_ud:
        out = np.flipud(out)
        y0, y1 = -y1, -y0

    for _ in range(rot_cw_steps % 4):
        out = np.rot90(out, k=-1)
        # 90° CW: (x, y) -> (y, -x). Extent transforms accordingly.
        x0, x1, y0, y1 = y0, y1, -x1, -x0

    return out, (x0, x1, y0, y1)
