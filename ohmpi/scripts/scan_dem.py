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


_GRID = None


def _load_grid():
    global _GRID
    if _GRID is None:
        build_grid()
        d = np.load(CACHE)
        _GRID = (d["grid"], tuple(d["ext"]), float(d["binsize"]))
    return _GRID


def sample_height(Xo, Yo):
    """Nearest-bin scan height at oriented coords (NaN-filled holes interpolated
    by a small neighbourhood median)."""
    grid, (x0, x1, y0, y1), b = _load_grid()
    nx, ny = grid.shape
    Xo = np.atleast_1d(Xo).astype(float)
    Yo = np.atleast_1d(Yo).astype(float)
    ix = np.clip(((Xo - x0) / b).astype(int), 0, nx - 1)
    iy = np.clip(((Yo - y0) / b).astype(int), 0, ny - 1)
    out = grid[ix, iy]
    # fill any NaN from a 7x7 neighbourhood median
    for k in np.where(np.isnan(out))[0]:
        i, j = ix[k], iy[k]
        w = grid[max(0, i - 3):i + 4, max(0, j - 3):j + 4]
        if np.isfinite(w).any():
            out[k] = np.nanmedian(w)
    return out


def elevation(x_world, y_world):
    """Scan-derived elevation at canonical world (x, y)."""
    Xo, Yo = world_to_scan(x_world, y_world)
    return sample_height(Xo, Yo)


if __name__ == "__main__":
    print(f"similarity: scale={SCALE:.4f}  angle={ANGLE_DEG:.2f} deg  (no reflection)")
    build_grid(force=True)
