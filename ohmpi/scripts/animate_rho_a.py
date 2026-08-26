"""Animated GIF of apparent resistivity pseudosection per electrode line,
with closest soil-moisture sensor (40 cm) and precipitation overlaid.

One GIF per line (A–D), ~250 frames, one frame per survey day.
Each frame has three panels:

  top    : daily precipitation (bar); gauge-fault window (post-2025-06-22) greyed
  middle : VWC 40 cm for the closest SMS pair, full timeseries + date marker
  bottom : ρ_a pseudosection — scatter of (midpoint position, pseudodepth, ρ_a)
           for all kept quads in that survey, both dipdip and wenner overlaid

Pseudosection coordinates:
  x_mid   = mean of rotated x-coords of the four electrodes (projected onto line)
  depth   = half the 3D distance between midpoint(A,B) and midpoint(M,N)
  colour  = ρ_a [Ω·m] on a fixed scale set to [p5, p95] across the whole campaign
"""

from __future__ import annotations

import sys
import warnings
from datetime import date
from pathlib import Path

# put ohmpi/scripts on path for ohmpi_loader + geometry imports
sys.path.insert(0, str(Path(__file__).parent))

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import polars as pl
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

# ── repo paths ──────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]

from ohmpi_loader import build_survey_index  # noqa: E402 (after sys.path insert)
from swale.config import load_settings
from swale.loader import load_swale_dataset

R_TABLE   = REPO / "ohmpi" / "cache" / "r_table.parquet"
ELEC_CSV  = REPO / "plots" / "12d_electrode_locations_rot180.csv"
OUT_DIR   = REPO / "ohmpi" / "plots" / "animations"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RAIN_CUTOFF = date(2025, 6, 22)   # gauge failure after this date
LINES       = ["A", "B", "C", "D"]

# closest SMS label → sensor IDs (from 12d spatial match)
LINE_SMS: dict[str, list[str]] = {
    "A": ["SMS03", "SMS04", "SMS05"],
    "B": ["SMS01", "SMS02"],
    "C": ["SMS10"],
    "D": ["SMS03", "SMS04", "SMS05"],
}

FPS        = 8       # frames per second in the GIF
DPI        = 100
FIGSIZE    = (12, 9)


# ── electrode geometry helpers ───────────────────────────────────────────────

def load_rotated_coords() -> dict[int, tuple[float, float, float]]:
    """OhmPi channel → (x_rot180, y_rot180, Z_av) using corrected XY frame.

    XY are the 180°-rotated positions from 12d; Z_av is negated to give true
    relative height (B upslope/highest, E downslope/lowest).
    """
    df  = pl.read_csv(ELEC_CSV)
    merged = _merged_table().join(
        df.select("Electrode number for survey", "x_rot180", "y_rot180", "Z_av"),
        on="Electrode number for survey",
        how="left",
    )
    return {
        int(ch): (float(x), float(y), float(-z))   # negate Z → true height
        for ch, x, y, z in merged.select(
            "Ohmpi channel", "x_rot180", "y_rot180", "Z_av"
        ).iter_rows()
    }


_MERGED_TABLE: pl.DataFrame | None = None

def _merged_table() -> pl.DataFrame:
    global _MERGED_TABLE
    if _MERGED_TABLE is None:
        _MERGED_TABLE = pl.read_excel(
            Path(__file__).parents[1] / "ohmpi_geometries" / "merged_electrode_table.xlsx"
        )
    return _MERGED_TABLE


def line_axis(line: str, coords: dict[int, tuple[float, float, float]]) -> np.ndarray:
    """Unit vector of the principal axis for this line (2D, rotated frame)."""
    chs = _merged_table().filter(pl.col("Line") == line)["Ohmpi channel"].to_list()
    pts = np.array([[coords[ch][0], coords[ch][1]] for ch in chs if ch in coords])
    _, vecs = np.linalg.eigh(np.cov(pts.T))
    return vecs[:, -1]   # principal axis (largest eigenvalue)


def pseudo_coords(
    coords: dict[int, tuple[float, float, float]],
    a: int, b: int, m: int, n: int,
    axis: np.ndarray,
) -> tuple[float, float] | None:
    """(along-line position, pseudodepth) for one quad, or None if missing.

    along-line = projection of the quad midpoint onto `axis`.
    pseudodepth = half the 3D separation between midpoint(AB) and midpoint(MN).
    """
    try:
        A, B, M, N = coords[a], coords[b], coords[m], coords[n]
    except KeyError:
        return None
    mid_xy  = np.array([(A[0]+B[0]+M[0]+N[0])/4, (A[1]+B[1]+M[1]+N[1])/4])
    pos     = float(np.dot(mid_xy, axis))
    ab_mid  = np.array([(A[0]+B[0])/2, (A[1]+B[1])/2, (A[2]+B[2])/2])
    mn_mid  = np.array([(M[0]+N[0])/2, (M[1]+N[1])/2, (M[2]+N[2])/2])
    depth   = float(np.linalg.norm(ab_mid - mn_mid) / 2)
    return pos, depth


# ── data loading ─────────────────────────────────────────────────────────────

def load_rho_pseudosection(
    line: str,
    coords: dict[int, tuple[float, float, float]],
) -> pl.DataFrame:
    """All kept, non-bad-day ρ_a rows for this line with pseudosection coords."""
    ax = line_axis(line, coords)
    r  = pl.read_parquet(R_TABLE)
    sub = r.filter(
        pl.col("keep")
        & ~pl.col("drop_day")
        & pl.col("rho_a").is_not_null()
        & (pl.col("line") == line)
    )
    rows = []
    for row in sub.iter_rows(named=True):
        pc = pseudo_coords(coords, row["a"], row["b"], row["m"], row["n"], ax)
        if pc is None:
            continue
        rows.append({
            "day":    row["day"],
            "array":  row["array"],
            "quad":   row["quad"],
            "rho_a":  row["rho_a"],
            "x_mid":  pc[0],
            "depth":  pc[1],
        })
    return pl.DataFrame(rows).sort("day")


def load_swale_data():
    """Return (daily_rain, vwc_daily) for the animation timeseries."""
    cfg = load_settings()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(cfg.data_root, cfg.metadata_xlsx, grid="none")

    # daily rain
    rain = (
        df.filter(pl.col("variable") == "precipitation")
        .with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("day")
        .agg(rain_mm=pl.col("value").sum())
        .sort("day")
    )

    # 40 cm VWC, daily mean per sensor_id
    vwc = (
        df.filter((pl.col("variable") == "moisture") & (pl.col("depth_cm") == 40))
        .with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("sensor_id", "day")
        .agg(vwc=pl.col("value").mean())
        .sort("sensor_id", "day")
    )

    return rain, vwc


# ── animation ────────────────────────────────────────────────────────────────

def make_gif(line: str, ps: pl.DataFrame, rain: pl.DataFrame, vwc: pl.DataFrame):
    from matplotlib.lines import Line2D

    sensor_ids = LINE_SMS[line]
    vwc_line = (
        vwc.filter(pl.col("sensor_id").is_in(sensor_ids))
        .group_by("day").agg(vwc=pl.col("vwc").mean()).sort("day")
    )

    days = sorted(ps["day"].unique().to_list())
    if not days:
        print(f"  line {line}: no data, skipping"); return

    # ρ_a colour scale
    rho_all = ps["rho_a"].to_numpy()
    vmin, vmax = float(np.nanpercentile(rho_all, 5)), float(np.nanpercentile(rho_all, 95))
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap("RdBu_r")

    # --- unified x-axis: one index per calendar day across the full span ---
    all_days = sorted(set(
        rain["day"].to_list() + vwc_line["day"].to_list() + days
    ))
    day_idx = {d: i for i, d in enumerate(all_days)}
    N = len(all_days)

    # rain arrays indexed into all_days
    rain_xi = np.array([day_idx[d] for d in rain["day"].to_list()])
    rain_mm = rain["rain_mm"].to_numpy()
    rain_col = ["#2196F3" if d <= RAIN_CUTOFF else "#aaaaaa"
                for d in rain["day"].to_list()]

    # grey fault-window span (x index of first day after cutoff)
    fault_start = next((i for i, d in enumerate(all_days) if d > RAIN_CUTOFF), N)

    # VWC array
    vwc_xi = np.array([day_idx[d] for d in vwc_line["day"].to_list()])
    vwc_vv = vwc_line["vwc"].to_numpy()
    vwc_ymin = max(0.0, float(np.nanmin(vwc_vv)) - 0.02)
    vwc_ymax = float(np.nanmax(vwc_vv)) + 0.02

    # monthly x-tick positions
    tick_xi, tick_lb = [], []
    for d in all_days:
        if d.day == 1:
            tick_xi.append(day_idx[d])
            tick_lb.append(d.strftime("%b\n%Y") if d.month == 1 else d.strftime("%b"))

    # pseudosection limits
    x_all = ps["x_mid"].to_numpy(); d_all = ps["depth"].to_numpy()
    xmin, xmax = float(x_all.min()) - 0.3, float(x_all.max()) + 0.3
    dmax = float(np.nanpercentile(d_all, 99)) * 1.15

    # --- figure layout ---
    fig = plt.figure(figsize=FIGSIZE)
    gs  = fig.add_gridspec(3, 2, height_ratios=[1, 1.4, 2.6],
                           width_ratios=[20, 1], hspace=0.40, wspace=0.05)
    ax_rain = fig.add_subplot(gs[0, 0])
    ax_vwc  = fig.add_subplot(gs[1, 0], sharex=ax_rain)
    ax_ps   = fig.add_subplot(gs[2, 0])
    ax_cb   = fig.add_subplot(gs[2, 1])

    plt.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=ax_cb).set_label(
        "ρ_a [Ω·m]", fontsize=9)

    def draw_frame(i):
        day = days[i]
        xi_now = day_idx[day]
        ax_rain.cla(); ax_vwc.cla(); ax_ps.cla()

        # rain
        ax_rain.bar(rain_xi, rain_mm, color=rain_col, width=1.0, align="center")
        ax_rain.axvspan(fault_start, N, color="#dddddd", alpha=0.5, zorder=0)
        ax_rain.axvline(xi_now, color="k", lw=1.2, zorder=5)
        ax_rain.set_xlim(0, N - 1)
        ax_rain.set_ylim(0, max(float(rain_mm.max()), 1) * 1.15)
        ax_rain.set_ylabel("rain [mm/d]", fontsize=8)
        ax_rain.set_xticks([]); ax_rain.xaxis.set_tick_params(labelbottom=False)
        ax_rain.text(0.99, 0.88, "grey = gauge fault", transform=ax_rain.transAxes,
                     fontsize=7, color="#888", ha="right")
        ax_rain.set_title(
            f"Line {line}  ·  {day}  ·  SMS {', '.join(s.replace('SMS','') for s in sensor_ids)}  (40 cm VWC)",
            fontsize=10, loc="left", fontweight="bold")

        # VWC
        ax_vwc.plot(vwc_xi, vwc_vv, "-", color="steelblue", lw=1.2)
        ax_vwc.axvline(xi_now, color="k", lw=1.2, zorder=5)
        ax_vwc.set_ylim(vwc_ymin, vwc_ymax)
        ax_vwc.set_ylabel("VWC [m³/m³]", fontsize=8)
        ax_vwc.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        ax_vwc.set_xticks(tick_xi); ax_vwc.set_xticklabels(tick_lb, fontsize=7)
        ax_vwc.set_xlim(0, N - 1)

        # pseudosection
        day_data = ps.filter(pl.col("day") == day)
        if day_data.height:
            x   = day_data["x_mid"].to_numpy()
            d   = day_data["depth"].to_numpy()
            rho = day_data["rho_a"].to_numpy()
            for xi, di, ri, arr in zip(x, d, rho,
                                        day_data["array"].to_list()):
                ax_ps.scatter(xi, di, color=cmap(norm(ri)),
                              marker="o" if arr == "dipdip" else "^",
                              s=110, edgecolor="k", linewidth=0.5, zorder=3)
        ax_ps.set_xlim(xmin, xmax); ax_ps.set_ylim(dmax, 0)
        ax_ps.set_xlabel("along-line position [m]", fontsize=9)
        ax_ps.set_ylabel("pseudo-depth [m]", fontsize=9)
        ax_ps.grid(alpha=0.25)
        ax_ps.legend(handles=[
            Line2D([0],[0], marker="o", ls="none", mfc="grey", mec="k", ms=7, label="dipdip"),
            Line2D([0],[0], marker="^", ls="none", mfc="grey", mec="k", ms=7, label="wenner"),
        ], loc="lower right", fontsize=8, framealpha=0.8)
        ax_ps.set_title(
            f"ρ_a pseudosection  ({day_data.height} quads)  "
            f"[{vmin:.1f}–{vmax:.1f} Ω·m]",
            fontsize=9, loc="left")

    anim = FuncAnimation(fig, draw_frame, frames=len(days), blit=False)
    out  = OUT_DIR / f"rho_a_line_{line}.gif"
    anim.save(str(out), writer=PillowWriter(fps=FPS), dpi=DPI)
    plt.close(fig)
    print(f"  saved {out.relative_to(REPO)}  ({len(days)} frames)")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("loading electrode coordinates ...")
    coords = load_rotated_coords()

    print("loading soil + rain data ...")
    rain, vwc = load_swale_data()

    for line in LINES:
        print(f"\nline {line}:")
        print("  computing pseudosection coordinates ...")
        ps = load_rho_pseudosection(line, coords)
        print(f"  {ps.height} quad-survey rows, {ps['day'].n_unique()} survey days")
        print("  rendering GIF ...")
        make_gif(line, ps, rain, vwc)

    print("\ndone →", OUT_DIR)
