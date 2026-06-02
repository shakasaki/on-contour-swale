"""Electrode geometry: OhmPi channel → real coordinates, and the 3D geometric factor.

The quad columns a/b/m/n in the survey files are **OhmPi channel numbers**
(verified set-equal to the per-line channels in merged_electrode_table.xlsx,
gaps and all — e.g. line A is 1–7, 9, 10, 11, skipping the unused MUX channels
8/12). Real surveyed positions (X_av, Y_av, Z_av, ~0.68 m spacing, ~0.6 m of
topography per line) live in that table, keyed by channel.

Do NOT use ohmpi_geometries/electrode_geometry.csv for this: it numbers
electrodes 1–60 sequentially with no gaps and an idealised flat 1 m grid, so its
"electrode 8" is not OhmPi channel 8, and its spacing/topography are wrong.

Geometric factor (3D, half-space surface convention):

    K = 2π / [ (1/r_am − 1/r_bm) − (1/r_an − 1/r_bn) ]

with r_xy the 3D Euclidean distance between electrodes (topography included via
Z). K is signed: co-linear dipole-dipole gives K < 0, so ρ_a = K·R recovers a
positive apparent resistivity from the (negative) dipole-dipole R. True
topographic correction beyond this analytic K belongs in the inversion mesh.

The test-circuit channels (60–64, the ~100 Ω reference resistor) are not ground
electrodes and have no coordinates; quads touching them get K = ρ_a = null.

KNOWN COORDINATE ISSUES (being fixed upstream — corrected coords to be pushed):
  - The Z sign in merged_electrode_table.xlsx is inverted vs true elevation:
    negating Z makes line B the highest (upslope) and E the lowest, and line A
    descend monotonically with electrode number — matching the field. As stored,
    B reads lowest, which is wrong.
  - The electrode XY frame is not registered to the DEM; a best-fit alignment
    (transpose + flip) only reaches ~0.2 m RMS. Proper registration needs
    surveyed control points.
Neither affects K or ρ_a: the geometric factor depends only on inter-electrode
distances, which are invariant under reflection, rotation, and translation. The
issues matter only for placing results on the DEM map / inversion mesh.
"""

from __future__ import annotations

import math
from pathlib import Path

import polars as pl

GEOM_XLSX = (
    Path(__file__).resolve().parents[1]
    / "ohmpi_geometries"
    / "merged_electrode_table.xlsx"
)


def load_electrode_coords() -> dict[int, tuple[float, float, float]]:
    """Map OhmPi channel → (X_av, Y_av, Z_av) in the relative survey frame."""
    m = pl.read_excel(GEOM_XLSX)
    return {
        int(ch): (float(x), float(y), float(z))
        for ch, x, y, z in m.select(
            "Ohmpi channel", "X_av", "Y_av", "Z_av"
        ).iter_rows()
    }


def _dist(p: tuple[float, float, float], q: tuple[float, float, float]) -> float:
    return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def geometric_factor(
    coords: dict[int, tuple[float, float, float]],
    a: int,
    b: int,
    m: int,
    n: int,
) -> float | None:
    """Signed 3D half-space geometric factor for quad (a, b, m, n).

    Returns None if any electrode lacks coordinates (e.g. test-circuit channels)
    or the configuration is degenerate (denominator ≈ 0).
    """
    try:
        A, B, M, N = coords[a], coords[b], coords[m], coords[n]
    except KeyError:
        return None
    denom = (1 / _dist(A, M) - 1 / _dist(B, M)) - (1 / _dist(A, N) - 1 / _dist(B, N))
    if abs(denom) < 1e-9:
        return None
    return 2.0 * math.pi / denom


def add_geometry(df: pl.DataFrame) -> pl.DataFrame:
    """Attach `K` and `rho_a` (= K·R) to a frame carrying a,b,m,n and R.

    Rows whose quad touches a coordinate-less channel get K = rho_a = null.
    """
    coords = load_electrode_coords()
    k = [
        geometric_factor(coords, a, b, m, n)
        for a, b, m, n in df.select("a", "b", "m", "n").iter_rows()
    ]
    return df.with_columns(pl.Series("K", k, dtype=pl.Float64)).with_columns(
        (pl.col("K") * pl.col("R")).alias("rho_a")
    )
