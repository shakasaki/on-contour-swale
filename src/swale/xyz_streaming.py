"""Streaming readers for large ``.xyz`` point-cloud files.

Each ``.xyz`` file under ``data/DEM_xyz/`` is a space- or comma-
separated table with columns ``X V W R G B``, where the scanner uses a
**Y-up** convention: V is elevation (vertical) and W is the second
horizontal axis. We swap them on read so downstream code can treat
the returned arrays as standard (X, Y_horizontal, Z_elevation).

Each file can reach ~1 GB / ~12 M points; loading the whole file into
RAM is wasteful when we only need summary statistics or a 2-D
mean-Z grid. The helpers here stream the file in fixed-size chunks
and accumulate into bounded-memory buffers.

Two-pass workflow:

1. :func:`summarize_xyz` — one quick pass to learn point count and XYZ
   extents. No data retained.
2. :func:`histogram2d_xyz` — second pass given the extents from step 1,
   accumulating per-bin Σz and count into a 2-D grid (memory ~8 MB at
   1000×1000 bins, independent of file size).

Both helpers are pure numpy + the standard library; no pandas/polars.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Iterator

import numpy as np


# Chunk size in number of input lines. Larger = fewer numpy round-trips
# but more transient RAM. 200 k lines * 6 cols * 8 bytes ≈ 9.6 MB.
DEFAULT_CHUNK_LINES = 200_000


@dataclass(frozen=True)
class XYZSummary:
    """Per-file extents and point count."""
    path: Path
    n_points: int
    x_min: float; x_max: float
    y_min: float; y_max: float
    z_min: float; z_max: float
    file_size_bytes: int


def _detect_separator(path: Path) -> str | None:
    """Return ``,`` for comma-separated files, ``None`` for whitespace.

    Some scans land as space-separated ``X Y Z R G B`` and others as
    ``,``-separated. We sniff the first non-empty line.
    """
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            return "," if "," in line else None
    return None


def _iter_chunks(path: Path, chunk_lines: int) -> Iterator[np.ndarray]:
    """Yield successive numpy arrays of shape ``(N, 3)`` as (X, Y, Z).

    Lines are parsed via ``str.split`` (or ``str.split(",")`` when the
    file uses CSV). RGB columns are dropped.

    Column convention swap: the source files use Y-up (col0=X,
    col1=vertical, col2=Y-horizontal). We swap cols 1 and 2 so the
    returned (X, Y, Z) follow the standard "Z-up" convention used
    everywhere else in this project (including ``Mesh_swale_site.vtk``).
    """
    sep = _detect_separator(path)
    with path.open() as f:
        while True:
            chunk = list(islice(f, chunk_lines))
            if not chunk:
                break
            flat: list[str] = []
            if sep is None:
                for line in chunk:
                    toks = line.split(maxsplit=3)
                    if len(toks) < 3:
                        continue
                    # toks = [X, V (vertical), W (Y-horizontal), ...]
                    # We re-order to (X, W, V) = (X, Y, Z) in Z-up.
                    flat.append(toks[0]); flat.append(toks[2]); flat.append(toks[1])
            else:
                for line in chunk:
                    toks = line.split(sep, maxsplit=3)
                    if len(toks) < 3:
                        continue
                    flat.append(toks[0]); flat.append(toks[2]); flat.append(toks[1])
            if not flat:
                continue
            arr = np.asarray(flat, dtype=np.float64).reshape(-1, 3)
            yield arr


def summarize_xyz(
    path: Path,
    *,
    chunk_lines: int = DEFAULT_CHUNK_LINES,
) -> XYZSummary:
    """Stream-scan ``path`` and return ``XYZSummary``.

    Memory: O(chunk_lines). Time: I/O-bound.

    Args:
        path: Path to the ``.xyz`` file.
        chunk_lines: Lines per parsed chunk.

    Returns:
        Summary with point count and XYZ min/max.
    """
    n = 0
    xmin = ymin = zmin = np.inf
    xmax = ymax = zmax = -np.inf

    for arr in _iter_chunks(path, chunk_lines):
        n += arr.shape[0]
        xmin = min(xmin, arr[:, 0].min())
        xmax = max(xmax, arr[:, 0].max())
        ymin = min(ymin, arr[:, 1].min())
        ymax = max(ymax, arr[:, 1].max())
        zmin = min(zmin, arr[:, 2].min())
        zmax = max(zmax, arr[:, 2].max())

    return XYZSummary(
        path=path, n_points=n,
        x_min=float(xmin), x_max=float(xmax),
        y_min=float(ymin), y_max=float(ymax),
        z_min=float(zmin), z_max=float(zmax),
        file_size_bytes=path.stat().st_size,
    )


def histogram2d_xyz(
    path: Path,
    summary: XYZSummary,
    *,
    bins_xy: tuple[int, int] = (1000, 1000),
    chunk_lines: int = DEFAULT_CHUNK_LINES,
) -> tuple[np.ndarray, np.ndarray]:
    """Stream-accumulate a 2-D ``(Σz, count)`` grid over the file's XY extent.

    The grid's edges come from ``summary``. Each chunk contributes
    ``np.add.at`` into the running ``zsum`` and ``count`` arrays.

    Args:
        path: Same path used for the summary.
        summary: Extents from a prior :func:`summarize_xyz` call.
        bins_xy: Grid resolution in (nx, ny). 1000×1000 ≈ 8 MB per array.
        chunk_lines: Lines per parsed chunk.

    Returns:
        ``(zsum, count)`` — both of shape ``(nx, ny)``. Caller computes
        ``mean_z = zsum / count`` with the count-zero mask as needed.
    """
    nx, ny = bins_xy
    zsum = np.zeros((nx, ny), dtype=np.float64)
    count = np.zeros((nx, ny), dtype=np.int64)

    # Edges: protect against zero-width axes (single Z plane is still ok
    # for XY mapping, but XY span needs > 0).
    x0, x1 = summary.x_min, summary.x_max
    y0, y1 = summary.y_min, summary.y_max
    dx = max(x1 - x0, 1e-9)
    dy = max(y1 - y0, 1e-9)

    for arr in _iter_chunks(path, chunk_lines):
        x = arr[:, 0]; y = arr[:, 1]; z = arr[:, 2]
        ix = np.clip(((x - x0) / dx * nx).astype(np.int64), 0, nx - 1)
        iy = np.clip(((y - y0) / dy * ny).astype(np.int64), 0, ny - 1)
        np.add.at(zsum, (ix, iy), z)
        np.add.at(count, (ix, iy), 1)

    return zsum, count
