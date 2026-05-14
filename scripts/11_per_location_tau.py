"""Per-location recession τ on a plan-view map (one panel per depth).

Reads ``plots/07_recession_fits.csv`` (per-event exponential fits) and
aggregates to one (median tau, N good fits) per sensor. Plots each
sensor at its (X, Y) location from ``data/SMS_locations.csv``, with
marker colour = log10(median tau_h) and marker size scaled to N. One
panel for 10 cm sensors, one for 40 cm.

The point of this view: the per-event tau already strips out the
absolute VWC baseline, so a slow tau means the sensor is genuinely
draining slowly - independent of how wet that local soil happens to
be at rest. We can then see whether the slow-tau signature clusters
spatially (e.g., at the mound + Bottom slope 2) or is uniform across
the swale.

Outputs:
  * plots/11_per_location_tau_map.png

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/11_per_location_tau.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.config import load_settings
from swale.sites import sensor_pairs
from swale.spatial_frame import load_canonical_dem_mesh

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"
FITS_CSV = ROOT / "plots" / "07_recession_fits.csv"
DEM_MESH = ROOT / "data" / "DEM" / "Mesh_swale_site.vtk"

OUT_PNG = ROOT / "plots" / "11_per_location_tau_map.png"

# Filter criteria — match what 07_recession_fits uses for its
# "representative events" plot so the τ aggregation pools the same
# population of fits we trusted there.
R2_MIN = 0.70
TAU_MIN_H = 5.0
TAU_MAX_H = 500.0
N_MIN_GOOD_FITS = 3  # require at least this many events to report a per-sensor median

# Visual tunables
DEPTHS = [10, 40]
MARKER_SIZE_PER_FIT = 30        # base marker size grows with N good fits
MARKER_SIZE_MIN = 80
MARKER_SIZE_MAX = 700
LABEL_PIXEL_OFFSET = 8
CMAP_TAU = "magma_r"            # darker = slower drainage = higher tau


def get_dem_bbox() -> tuple[float, float, float, float] | None:
    if not DEM_MESH.exists():
        return None
    m = load_canonical_dem_mesh(DEM_MESH)
    b = m.bounds
    return b.x_min, b.x_max, b.y_min, b.y_max


def aggregate_tau(df: pl.DataFrame) -> pl.DataFrame:
    """Per-(sensor_id, depth_cm): median tau_h, p25, p75, N good fits."""
    good = df.filter(
        (pl.col("exp_r2") >= R2_MIN)
        & (pl.col("exp_tau_h") >= TAU_MIN_H)
        & (pl.col("exp_tau_h") <= TAU_MAX_H)
    )
    return (
        good.group_by(["sensor_id", "depth_cm", "treatment", "location"])
            .agg([
                pl.col("exp_tau_h").median().alias("tau_h_median"),
                pl.col("exp_tau_h").quantile(0.25).alias("tau_h_q25"),
                pl.col("exp_tau_h").quantile(0.75).alias("tau_h_q75"),
                pl.len().alias("n_good_fits"),
            ])
            .sort(["depth_cm", "treatment", "sensor_id"])
    )


def plot_map(ax, depth_cm: int, agg: pl.DataFrame,
              pairs_by_sid: dict, dem_bbox: tuple | None,
              vmin: float, vmax: float):
    """Render one map panel for the given depth."""
    sub = agg.filter(
        (pl.col("depth_cm") == depth_cm)
        & (pl.col("n_good_fits") >= N_MIN_GOOD_FITS)
    )

    xs, ys, taus, ns, sids, labels = [], [], [], [], [], []
    for row in sub.iter_rows(named=True):
        sid = row["sensor_id"]
        if sid not in pairs_by_sid:
            continue
        x, y = pairs_by_sid[sid]
        xs.append(x); ys.append(y)
        taus.append(row["tau_h_median"])
        ns.append(int(row["n_good_fits"]))
        sids.append(sid)
        labels.append(row["location"])

    if not xs:
        ax.text(0.5, 0.5, f"no good fits at {depth_cm} cm",
                ha="center", va="center", transform=ax.transAxes)
        return

    sizes = np.clip(np.array(ns) * MARKER_SIZE_PER_FIT,
                     MARKER_SIZE_MIN, MARKER_SIZE_MAX)

    sc = ax.scatter(
        xs, ys, c=np.log10(taus), s=sizes,
        cmap=CMAP_TAU, vmin=np.log10(vmin), vmax=np.log10(vmax),
        edgecolors="black", linewidths=1.2, zorder=4,
    )

    # Labels: sensor ID + numeric tau next to each point
    for x, y, sid, tau, n in zip(xs, ys, sids, taus, ns):
        ax.annotate(
            f"{sid}\nτ={tau:.0f} h\n(n={n})",
            xy=(x, y),
            xytext=(LABEL_PIXEL_OFFSET, LABEL_PIXEL_OFFSET),
            textcoords="offset points",
            fontsize=8, ha="left", va="bottom",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "lightgrey",
                  "boxstyle": "round,pad=0.2"},
            zorder=5,
        )

    if dem_bbox is not None:
        bx0, bx1, by0, by1 = dem_bbox
        ax.plot([bx0, bx1, bx1, bx0, bx0],
                [by0, by0, by1, by1, by0],
                color="red", lw=1.2, alpha=0.5,
                label="Mesh_swale_site.vtk extent")
        ax.legend(loc="upper left", fontsize=8, frameon=True)

    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.set_title(f"{depth_cm} cm depth", fontsize=11, weight="bold")
    return sc


def main() -> None:
    OUT_PNG.parent.mkdir(exist_ok=True)
    print("Loading recession fits ...")
    fits = pl.read_csv(FITS_CSV)
    print(f"  {fits.height} events x sensors total")

    agg = aggregate_tau(fits)
    print(f"\nAggregated medians (R^2 >= {R2_MIN}, tau in "
          f"[{TAU_MIN_H}, {TAU_MAX_H}] h, n_good >= {N_MIN_GOOD_FITS}):")
    with pl.Config(tbl_rows=20):
        print(agg)

    pairs = sensor_pairs(LOCATIONS_CSV)
    pairs_by_sid = {sid: (p.x, p.y) for p in pairs for sid in p.sensor_ids}

    dem_bbox = get_dem_bbox()

    # Shared colour scale across both depths so the comparison is direct.
    good_taus = agg.filter(
        pl.col("n_good_fits") >= N_MIN_GOOD_FITS
    )["tau_h_median"].to_list()
    if not good_taus:
        raise RuntimeError("no sensors passed the n_good filter")
    vmin = max(min(good_taus), TAU_MIN_H)
    vmax = min(max(good_taus), TAU_MAX_H)
    print(f"\ntau colour scale: [{vmin:.0f}, {vmax:.0f}] h (log10)")

    fig, axes = plt.subplots(1, len(DEPTHS), figsize=(15, 7.5),
                              constrained_layout=True)
    sc_last = None
    for ax, depth in zip(axes, DEPTHS):
        sc = plot_map(ax, depth, agg, pairs_by_sid, dem_bbox, vmin, vmax)
        if sc is not None:
            sc_last = sc

    # Shared colorbar
    if sc_last is not None:
        cbar = fig.colorbar(sc_last, ax=axes, shrink=0.7, pad=0.02)
        cbar.set_label("log10(median recession τ, h)")
        # Mark friendly tick labels in hours
        ticks_h = [10, 24, 48, 100, 200, 500]
        cbar.set_ticks([np.log10(t) for t in ticks_h if vmin <= t <= vmax])
        cbar.set_ticklabels([f"{t} h" for t in ticks_h if vmin <= t <= vmax])

    fig.suptitle(
        f"Per-location recession τ (median across events with R^2 >= {R2_MIN}, "
        f"τ in [{TAU_MIN_H:.0f}, {TAU_MAX_H:.0f}] h)\n"
        f"Darker = slower drainage; marker size ∝ N good fits",
        fontsize=11, weight="bold",
    )

    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\nWrote {OUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
