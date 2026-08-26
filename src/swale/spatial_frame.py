"""Canonical spatial frame for the swale site.

All map-view plots in this project share one orientation:

    +X = East
    +Y = North
    +Z = up (vertical)

Loaders (``swale.sites.load_sensor_pairs``, ``load_canonical_dem_mesh``,
``swale.xyz_align.compute_or_load_histogram`` + the per-script rotation
table) apply the raw->canonical transform once, at load time, so every
downstream plot can draw natively with no ``ax.invert_*axis()`` calls.

The transform is a pair of sign flips read from
``config/settings.json``::

    "spatial_frame": {
      "raw_x_sign": -1,
      "raw_y_sign": -1
    }

For the Sadhana swale survey, raw X grew toward the West and raw Y grew
toward the South, so both signs invert. With ``raw_x_sign=-1`` and
``raw_y_sign=-1`` the canonical frame is a 180-degree rotation of the
raw frame, which matches the orientation in ``plots/12_dem_xy.png``
(swale on the left, control on the right, north at the top).

Three helpers cover the common needs:

* :func:`to_canonical_xy` — scalars or numpy arrays.
* :func:`to_canonical_extent` — ``(x_min, x_max, y_min, y_max)`` tuples
  for ``imshow``. Note: the min/max may swap after a sign flip; the
  return value re-sorts so ``x_min <= x_max``.
* :func:`to_canonical_mesh` / :func:`load_canonical_dem_mesh` —
  PyVista PolyData (returns a copy with transformed points).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import overload

import numpy as np

from swale.config import SpatialFrame, load_settings


def _frame() -> SpatialFrame:
    """Read the canonical-frame signs from settings (cached per call)."""
    return load_settings().spatial_frame


@overload
def to_canonical_xy(x: float, y: float) -> tuple[float, float]: ...
@overload
def to_canonical_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...
def to_canonical_xy(x, y):
    """Map raw (x, y) -> canonical (x', y') by element-wise sign flip."""
    sf = _frame()
    return sf.raw_x_sign * x, sf.raw_y_sign * y


def to_canonical_extent(
    extent: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Map an imshow ``(x_min, x_max, y_min, y_max)`` extent to canonical.

    A sign flip swaps min and max for that axis, so we sort the
    transformed pair so the returned ``x_min <= x_max`` and likewise
    for y. matplotlib accepts either ordering, but downstream callers
    sometimes inspect the values, so we keep the sorted convention.
    """
    sf = _frame()
    x0, x1 = sorted([sf.raw_x_sign * extent[0], sf.raw_x_sign * extent[1]])
    y0, y1 = sorted([sf.raw_y_sign * extent[2], sf.raw_y_sign * extent[3]])
    return x0, x1, y0, y1


def to_canonical_mesh(mesh):
    """Return a copy of a PyVista mesh with x, y flipped to canonical.

    Z is untouched (canonical Z is the same as raw Z: positive up).
    """
    import pyvista as pv  # local import keeps the module light when unused

    out: pv.PolyData = mesh.copy()
    sf = _frame()
    pts = np.asarray(out.points, dtype=float).copy()
    pts[:, 0] *= sf.raw_x_sign
    pts[:, 1] *= sf.raw_y_sign
    out.points = pts
    return out


def load_canonical_dem_mesh(path: Path):
    """``pv.read(path)`` + :func:`to_canonical_mesh` in one call."""
    import pyvista as pv

    if not Path(path).exists():
        raise FileNotFoundError(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mesh = pv.read(str(path))
    if mesh.n_points == 0:
        raise RuntimeError(f"no points in {path}")
    return to_canonical_mesh(mesh)


def xyz_rotation_table_default() -> tuple[bool, int]:
    """Default (flip_ud, rot_cw_steps) for .xyz scans in the canonical frame.

    The raw .xyz scans, after the streaming column swap (Y-up -> Z-up),
    sit in a frame that matches the raw DEM frame after a single vertical
    flip. To bring them all the way to canonical (raw DEM rotated 180
    degrees), we compose that flip with a 180-degree rotation. In the
    dihedral-group transform supported by ``swale.xyz_align.apply_transform``,
    that is ``(flip_ud=True, rot_cw_steps=2)``. Composition note:
    flip_ud + 180 = flip_lr in net effect, but expressing it as the
    composition keeps the per-scan rotation-table semantics intact
    (the rotation table aligns each scan to the raw DEM frame; this
    extra 180 is applied on top to reach canonical).
    """
    return True, 2
