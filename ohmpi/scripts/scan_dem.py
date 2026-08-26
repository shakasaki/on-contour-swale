"""Canonical surface model + electrode/sensor registration for this project.

DECISION (2026-06-05, confirmed against the data by the project owner):
the working DEM is the **24.05.30 terrestrial scan**
(`data/DEM_xyz/24.05.30_-_con_sw_and_for_11_59_00.xyz`), NOT `DEM_2024_07_25`
and NOT the per-electrode `Z_av` (whose sign was inverted and which had survey
spikes, e.g. line-A electrode 3).

The scan is delivered in the scanner's local frame. Its working ("oriented")
horizontal frame is::

    Xo = -z_scan      (scan column 3, negated)
    Yo = -x_scan      (scan column 1, negated)
    H  =  y_scan      (scan column 2)  -> height / elevation

Survey coordinates (electrodes in merged_electrode_table.xlsx, sensors in
SMS_locations.csv) live in the project canonical frame
(x = -X_raw, y = -Y_raw). They are mapped onto the scan with a 2-D similarity
(rotation + uniform scale + translation, **no reflection**) fitted from the two
soil-profile pits, which are visible as square depressions in the scan:

    world (close-to-swale pit)  (0.55, -9.77)  ->  scan (3.50,  1.00)
    world (far-from-swale pit) (12.43, -6.33)  ->  scan (16.00, -0.25)

Always use `world_to_scan()` to place survey points on the scan and
`elevation()` to read their topography. Do not negate Z_av anywhere.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "data" / "DEM_xyz" / "24.05.30_-_con_sw_and_for_11_59_00.xyz"
CACHE = REPO / "ohmpi" / "cache" / "scan_dem_grid.npz"

# --- 2-point similarity (no reflection): world canonical -> scan oriented ---
_W1, _S1 = complex(0.55, -9.77), complex(3.50, 1.00)    # close-to-swale pit
_W2, _S2 = complex(12.43, -6.33), complex(16.00, -0.25)  # far-from-swale pit
_FAC = (_S2 - _S1) / (_W2 - _W1)                          # scale * e^{i theta}

SCALE = abs(_FAC)
ANGLE_DEG = float(np.degrees(np.angle(_FAC)))

# scan-frame raster extent (covers the instrumented area with margin)
_EXT = (-8.0, 24.0, -16.0, 12.0)   # Xo_min, Xo_max, Yo_min, Yo_max
_BIN = 0.05                         # 5 cm

# low-pass: the raw 5 cm bin grid is noisy (scan speckle, vegetation). Smooth it
# with a NaN-aware Gaussian before sampling; sampling itself is bilinear. Set
# SMOOTH_SIGMA_BINS = 0 to disable smoothing (pure bilinear on the raw grid).
SMOOTH_SIGMA_BINS = 3.0             # 3 bins ≈ 15 cm


def world_to_scan(x, y):
    """Map canonical world (x, y) -> scan oriented (Xo, Yo). Arrays or scalars."""
    p = np.asarray(x) + 1j * np.asarray(y)
    q = _S1 + _FAC * (p - _W1)
    return np.real(q), np.imag(q)


def build_grid(force: bool = False) -> None:
    """Stream the scan once, bin to a mean-height grid in the oriented frame."""
    if CACHE.exists() and not force:
        return
    x0, x1, y0, y1 = _EXT
    nx = int(round((x1 - x0) / _BIN))
    ny = int(round((y1 - y0) / _BIN))
    hsum = np.zeros((nx, ny))
    hcnt = np.zeros((nx, ny))
    for chunk in pd.read_csv(SCAN, header=None, usecols=[0, 1, 2],
                             names=["x", "y", "z"], chunksize=2_000_000):
        Xo = -chunk["z"].to_numpy()
        Yo = -chunk["x"].to_numpy()
        H = chunk["y"].to_numpy()
        ix = ((Xo - x0) / _BIN).astype(int)
        iy = ((Yo - y0) / _BIN).astype(int)
        m = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        np.add.at(hsum, (ix[m], iy[m]), H[m])
        np.add.at(hcnt, (ix[m], iy[m]), 1.0)
    grid = np.where(hcnt > 0, hsum / np.maximum(hcnt, 1), np.nan)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, grid=grid, ext=np.array(_EXT), binsize=_BIN)
    print(f"built {CACHE.relative_to(REPO)}  ({nx}x{ny}, "
          f"{int(hcnt.sum()):,} pts binned)")


def _nan_gaussian(grid, sigma):
    """NaN-aware Gaussian low-pass: smooth values and the valid-mask separately,
    then divide, so holes don't bleed zeros into the surface."""
    from scipy.ndimage import gaussian_filter
    mask = np.isfinite(grid)
    vals = np.where(mask, grid, 0.0)
    num = gaussian_filter(vals, sigma, mode="nearest")
    den = gaussian_filter(mask.astype(float), sigma, mode="nearest")
    out = np.where(den > 1e-6, num / np.maximum(den, 1e-6), np.nan)
    return out


_GRID = None


def _load_grid():
    """Return (smoothed grid, ext, binsize). Grid is NaN-filled (neighbourhood
    median) then optionally Gaussian-smoothed per SMOOTH_SIGMA_BINS."""
    global _GRID
    if _GRID is None:
        build_grid()
        d = np.load(CACHE)
        grid = d["grid"]
        # NaN-aware Gaussian both low-passes the surface and fills holes within
        # ~sigma reach (so bilinear sampling sees no NaNs in the instrumented area)
        if SMOOTH_SIGMA_BINS > 0:
            grid = _nan_gaussian(grid, SMOOTH_SIGMA_BINS)
        _GRID = (grid, tuple(d["ext"]), float(d["binsize"]))
    return _GRID


def sample_height(Xo, Yo):
    """Bilinear scan height at oriented coords, on the smoothed grid."""
    grid, (x0, x1, y0, y1), b = _load_grid()
    nx, ny = grid.shape
    Xo = np.atleast_1d(Xo).astype(float)
    Yo = np.atleast_1d(Yo).astype(float)
    # continuous cell-centre coords: bin centre i sits at x0 + (i+0.5)*b
    fx = np.clip((Xo - x0) / b - 0.5, 0, nx - 1)
    fy = np.clip((Yo - y0) / b - 0.5, 0, ny - 1)
    i0 = np.floor(fx).astype(int); i1 = np.minimum(i0 + 1, nx - 1)
    j0 = np.floor(fy).astype(int); j1 = np.minimum(j0 + 1, ny - 1)
    wx = fx - i0; wy = fy - j0
    out = ((1 - wx) * (1 - wy) * grid[i0, j0]
           + wx * (1 - wy) * grid[i1, j0]
           + (1 - wx) * wy * grid[i0, j1]
           + wx * wy * grid[i1, j1])
    return out


def elevation(x_world, y_world):
    """Scan-derived elevation at canonical world (x, y)."""
    Xo, Yo = world_to_scan(x_world, y_world)
    return sample_height(Xo, Yo)


if __name__ == "__main__":
    print(f"similarity: scale={SCALE:.4f}  angle={ANGLE_DEG:.2f} deg  (no reflection)")
    build_grid(force=True)
