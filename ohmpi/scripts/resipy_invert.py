"""Time-lapse 2D ERT inversion of the OhmPi campaign with ResIPy (R2 via wine).

For each electrode line (A–D) this script:

  1. builds a 2D profile from the surveyed electrode positions — electrodes are
     projected onto the line's principal horizontal axis (along-line distance)
     and given their true elevation (negated Z, per the coordinate-frame note in
     geometry.py). R2 then computes the geometric factor *numerically* from this
     mesh, which is the whole point of inverting rather than using analytic K.
  2. writes one ProtocolDC file per daily survey: local 1-based electrode indices
     a b m n and the transfer resistance R (sign-flip estimator, the canonical
     column in r_table). Only `keep=True`, non-drop-day quads are used.
  3. inverts in two schemes:
       individual : every survey inverted independently  (reg_mode 0, batch)
       timelapse  : background-constrained inversion       (reg_mode 1)
                    — the first survey is the reference/starting model and every
                    later survey is regularised toward it.
  4. renders, per scheme, a 3-row frame for every timestep:
       row 1 : VWC at 10 cm (closest swale sensor) — full series + date marker
       row 2 : VWC at 40 cm                         — full series + date marker
       row 3 : the inverted resistivity section
     and stitches the frames into an animated GIF.

ResIPy 3.6.6 + numpy 1.26 ships a cython reciprocal routine that crashes on
read-only buffers; we route reciprocal calculation through the pure-pandas
fallback (computeReciprocalP) before importing Project.

Run from the repo root inside the `swale` conda env, e.g.::

    conda run -n swale python ohmpi/scripts/resipy_invert.py --line A --every 14
    conda run -n swale python ohmpi/scripts/resipy_invert.py --line all --every 1
"""

from __future__ import annotations

import argparse
import shutil
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

# ── ResIPy import with the read-only-buffer workaround ───────────────────────
from resipy.Survey import Survey as _SurvCls

_SurvCls.computeReciprocalC = _SurvCls.computeReciprocalP  # avoid cython crash
from resipy import Project  # noqa: E402

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402

# ── repo paths / imports ─────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
REPO = Path(__file__).resolve().parents[2]

import scan_dem  # noqa: E402  (registered 24.05.30 scan DEM for elevation)
from geometry import load_electrode_coords  # noqa: E402
from swale.config import load_settings  # noqa: E402
from swale.loader import load_swale_dataset  # noqa: E402

R_TABLE = REPO / "ohmpi" / "cache" / "r_table.parquet"
OUT_ROOT = REPO / "ohmpi" / "outputs" / "inversion"
WORK_ROOT = REPO / "ohmpi" / "outputs" / "resipy_work"

LINES = ["A", "B", "C", "D"]
ARRAY = "dipdip"          # dipole-dipole has the geometric coverage for imaging
RAIN_CUTOFF = date(2025, 6, 22)

# Closest swale soil-moisture location per line (from the 12d spatial match in
# animate_rho_a.py). We pull its 10 cm and 40 cm sensor from depth_cm at runtime.
LINE_SMS: dict[str, list[str]] = {
    "A": ["SMS03", "SMS04", "SMS05"],
    "B": ["SMS01", "SMS02"],
    "C": ["SMS10"],
    "D": ["SMS03", "SMS04", "SMS05"],
}

FPS = 6
DPI = 100
FIGSIZE = (12, 9)


# ── geometry ─────────────────────────────────────────────────────────────────

def build_profile(line: str, coords: dict[int, tuple[float, float, float]]):
    """Return (channels, elec Nx3 array, channel→local-index map) for `line`.

    Electrodes are ordered along the line's principal horizontal axis; column 0
    is along-line distance (m, starting at 0), column 2 is elevation (−Z).
    """
    r = pl.read_parquet(R_TABLE)
    d = r.filter((pl.col("line") == line) & (pl.col("array") == ARRAY) & pl.col("keep"))
    chans = sorted(
        c
        for c in set(
            d["a"].to_list() + d["b"].to_list() + d["m"].to_list() + d["n"].to_list()
        )
        if c in coords and c < 60  # drop test-circuit channels 60–64
    )
    P = np.array([coords[c] for c in chans])
    xy0 = P[:, :2] - P[:, :2].mean(0)
    axis = np.linalg.svd(xy0)[2][0]          # principal horizontal direction
    along = xy0 @ axis
    order = np.argsort(along)
    chans = [chans[i] for i in order]
    along = along[order] - along[order].min()
    # elevation from the registered 24.05.30 scan DEM (canonical world = -X_raw,
    # -Y_raw); see scan_dem.py. Replaces the wrong -Z_av convention.
    # TODO(2026-06-05): electrodes were installed BEFORE the mound was built, so
    # they should not follow the mound topography. Revisit — electrode Z likely
    # comes from Widmer's pre-mound survey, not from this (later) scan.
    xw = -P[order, 0]
    yw = -P[order, 1]
    elev = scan_dem.elevation(xw, yw)
    elec = np.zeros((len(chans), 3))
    elec[:, 0] = along
    elec[:, 2] = elev
    ch2idx = {c: i + 1 for i, c in enumerate(chans)}
    return chans, elec, ch2idx


def write_protocols(line: str, ch2idx: dict[int, int], outdir: Path, every: int):
    """Write one ProtocolDC file per (subsampled) survey. Return [(date, path)]."""
    r = pl.read_parquet(R_TABLE)
    d = r.filter(
        (pl.col("line") == line)
        & (pl.col("array") == ARRAY)
        & pl.col("keep")
        & ~pl.col("drop_day")
        & pl.col("R").is_not_null()
    ).sort("timestamp")
    timestamps = d["timestamp"].unique().sort().to_list()[::every]

    if outdir.exists():
        shutil.rmtree(outdir)            # avoid stale protocol files from prior runs
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[date, Path]] = []
    for i, ts in enumerate(timestamps):
        s = d.filter(pl.col("timestamp") == ts)
        rows = [
            (ch2idx[a], ch2idx[b], ch2idx[m], ch2idx[n], R)
            for a, b, m, n, R in zip(s["a"], s["b"], s["m"], s["n"], s["R"])
            if all(x in ch2idx for x in (a, b, m, n))
        ]
        if len(rows) < 6:        # too few measurements to invert meaningfully
            continue
        path = outdir / f"protocol_{i:03d}.dat"
        with open(path, "w") as f:
            f.write(f"{len(rows)}\n")
            for j, (a, b, m, n, R) in enumerate(rows, 1):
                f.write(f"{j} {a} {b} {m} {n} {R:.6f}\n")
        written.append((ts.date(), path))
    return written


# ── soil moisture ────────────────────────────────────────────────────────────

def load_vwc():
    """Daily-mean VWC per (sensor_id, depth_cm) across the campaign."""
    cfg = load_settings()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(cfg.data_root, cfg.metadata_xlsx, grid="none")
    return (
        df.filter(pl.col("variable") == "moisture")
        .with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("sensor_id", "depth_cm", "day")
        .agg(vwc=pl.col("value").mean())
        .sort("day")
    )


def vwc_series(vwc: pl.DataFrame, line: str, depth: int):
    """(days, values) for the closest swale sensor of `line` at `depth` cm."""
    sub = (
        vwc.filter(
            pl.col("sensor_id").is_in(LINE_SMS[line]) & (pl.col("depth_cm") == depth)
        )
        .group_by("day")
        .agg(vwc=pl.col("vwc").mean())
        .sort("day")
    )
    return sub["day"].to_list(), sub["vwc"].to_numpy()


# ── inversion ────────────────────────────────────────────────────────────────

def run_inversion(line: str, mode: str, elec, protodir: Path, workdir: Path):
    """Run ResIPy for one line/scheme; return the Project with meshResults."""
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    k = Project(typ="R2", dirname=str(workdir))
    if mode == "individual":
        k.createBatchSurvey(str(protodir), ftype="ProtocolDC")
    else:
        k.createTimeLapseSurvey(str(protodir), ftype="ProtocolDC")
        k.param["reg_mode"] = 1          # background-constrained (first = ref)
    k.setElec(elec)                       # set AFTER import (import resets elec)
    # fmd (fine-mesh depth) must be given explicitly: the auto value collapses to
    # 0 on these short topographic profiles and gmsh then yields an empty mesh.
    k.createMesh(typ="trian", fmd=3.0)
    k.invert(parallel=False)   # parallel wine runs race on R2.out; keep serial
    return k


# ── rendering ────────────────────────────────────────────────────────────────

def render_gif(line, mode, k, frame_dates, vwc, outdir: Path):
    """3-row animation: VWC 10 cm, VWC 40 cm, inverted section. Returns gif path."""
    n = len(k.meshResults)
    if n == 0:
        print(f"  line {line} {mode}: no results"); return None
    frame_dates = frame_dates[:n]

    # global resistivity colour scale (5–95 pct across all timesteps, log-ish)
    allres = np.concatenate(
        [mr.df["Resistivity(ohm.m)"].to_numpy() for mr in k.meshResults]
    )
    vmin, vmax = np.nanpercentile(allres, [5, 95])

    d10, v10 = vwc_series(vwc, line, 10)
    d40, v40 = vwc_series(vwc, line, 40)

    framedir = outdir / "frames"
    framedir.mkdir(parents=True, exist_ok=True)

    def draw(i):
        fig.clf()
        gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 3],
                              width_ratios=[30, 1], hspace=0.45, wspace=0.04)
        ax10 = fig.add_subplot(gs[0, 0])
        ax40 = fig.add_subplot(gs[1, 0], sharex=ax10)
        axsec = fig.add_subplot(gs[2, 0])
        axcb = fig.add_subplot(gs[2, 1])
        now = frame_dates[i]

        for ax, dd, vv, dep, col in (
            (ax10, d10, v10, 10, "#1f77b4"),
            (ax40, d40, v40, 40, "#0b3d61"),
        ):
            if len(dd):
                ax.plot(dd, vv, "-", color=col, lw=1.0)
                ax.axvline(now, color="k", lw=1.3, zorder=5)
                ax.set_ylim(max(0.0, float(np.nanmin(vv)) - 0.02),
                            float(np.nanmax(vv)) + 0.02)
            ax.set_ylabel(f"VWC {dep}cm", fontsize=8)
            ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
            ax.grid(alpha=0.25)
        ax10.set_title(
            f"Line {line} · {mode} inversion · {now}  "
            f"(SMS {', '.join(s[3:] for s in LINE_SMS[line])})",
            fontsize=11, loc="left", fontweight="bold")
        ax10.tick_params(labelbottom=False)

        k.showResults(index=i, ax=axsec, attr="Resistivity(ohm.m)", sens=False,
                      color_map="viridis", vmin=vmin, vmax=vmax,
                      use_pyvista=False, color_bar=False)
        axsec.set_xlabel("along-line distance [m]", fontsize=9)
        axsec.set_ylabel("elevation [m]", fontsize=9)
        rms = getattr(k.meshResults[i], "rms", None) or ""
        axsec.set_title(
            f"Inverted resistivity [Ω·m]  ({vmin:.1f}–{vmax:.1f})  {rms}",
            fontsize=9, loc="left")
        sm = plt.cm.ScalarMappable(
            cmap="viridis", norm=plt.Normalize(vmin=vmin, vmax=vmax))
        plt.colorbar(sm, cax=axcb).set_label("ρ [Ω·m]", fontsize=8)

    fig = plt.figure(figsize=FIGSIZE)
    paths = []
    for i in range(n):
        draw(i)
        p = framedir / f"frame_{i:03d}.png"
        fig.savefig(p, dpi=DPI, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)

    # assemble GIF straight from the saved frames (avoids a second redraw pass)
    from PIL import Image

    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in paths]
    gif = outdir / f"line_{line}_{mode}.gif"
    imgs[0].save(str(gif), save_all=True, append_images=imgs[1:],
                 duration=int(1000 / FPS), loop=0)
    print(f"  saved {gif.relative_to(REPO)}  ({n} frames)")
    return gif


# ── driver ───────────────────────────────────────────────────────────────────

def process(line: str, modes: list[str], every: int, vwc):
    coords = load_electrode_coords()
    chans, elec, ch2idx = build_profile(line, coords)
    print(f"line {line}: {len(chans)} electrodes, channels {chans}")

    protodir = WORK_ROOT / line / "protocols"
    written = write_protocols(line, ch2idx, protodir, every)
    frame_dates = [d for d, _ in written]
    print(f"  {len(written)} survey frames (every {every})")
    if not written:
        print("  no usable surveys, skipping"); return

    for mode in modes:
        print(f"  inverting [{mode}] ...")
        workdir = WORK_ROOT / line / mode
        k = run_inversion(line, mode, elec, protodir, workdir)
        outdir = OUT_ROOT / line / mode
        outdir.mkdir(parents=True, exist_ok=True)
        render_gif(line, mode, k, frame_dates, vwc, outdir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", default="A", help="A|B|C|D|all")
    ap.add_argument("--mode", default="both",
                    choices=["individual", "timelapse", "both"])
    ap.add_argument("--every", type=int, default=1,
                    help="subsample: keep every Nth survey (1 = all)")
    args = ap.parse_args()

    lines = LINES if args.line == "all" else [args.line]
    modes = (["individual", "timelapse"] if args.mode == "both" else [args.mode])

    print("loading soil-moisture data ...")
    vwc = load_vwc()
    for line in lines:
        process(line, modes, args.every, vwc)
    print("done →", OUT_ROOT)


if __name__ == "__main__":
    main()
