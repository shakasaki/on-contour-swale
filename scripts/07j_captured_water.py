"""Quantify event-by-event water captured by the swale vs control.

Per event × sensor, the rising-limb fitter (`05_rising_limb_metrics.py`)
already reports `delta_vwc = peak_vwc − baseline_vwc`. This script
turns ΔVWC into an **mm-equivalent water column** for an
interpretable swale-vs-control comparison.

Conversion
----------
Each TEROS-12 reading is treated as the bulk VWC of a representative
layer around the sensor:

    10 cm sensor  →  layer 0 – 25 cm  →  thickness 0.25 m
    40 cm sensor  →  layer 25 – 65 cm →  thickness 0.40 m

Water added to a layer at peak = ΔVWC (m³/m³) × thickness (m) × 1000
(m → mm). Column total = sum across both layers.

Three views per slope position
------------------------------
(a) ΔVWC distribution per sensor, slope-paired (4 sensors: control 10,
    swale 10, control 40, swale 40).
(b) Per-event (swale − control) ΔVWC distribution at each depth.
    Positive median = swale captures more on a typical event.
(c) Cumulative mm of water captured across all 94 events at each
    slope position — swale total, control total, and the absolute
    extra captured by the swale.

Slope positions:
    Top      — sw_t  vs cn_t
    Mid      — sw_m  vs cn_m
    Bottom 1 — sw_b1 vs cn_b
    Bottom 2 — sw_b2 vs cn_b   (same control twin as Bot 1)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

CSV_IN = Path("plots/05_rising_limb_metrics.csv")
OUT_DIR = Path("plots")

# Layer thicknesses for the column-water conversion.
THICK_M = {10: 0.25, 40: 0.40}   # m

# Slope-paired layout: (label, swale_id_by_depth, control_id_by_depth)
POSITIONS = [
    ("Top",
        {10: "SMS01", 40: "SMS02"},
        {10: "SMS11", 40: "SMS12"}),
    ("Mid / Mound",
        {10: "SMS04", 40: "SMS05"},
        {10: "SMS13", 40: "SMS14"}),
    ("Bottom 1",
        {10: "SMS06", 40: "SMS07"},
        {10: "SMS15", 40: "SMS16"}),
    ("Bottom 2",
        {10: "SMS08", 40: "SMS09"},
        {10: "SMS15", 40: "SMS16"}),
]

COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"


def vwc_to_mm(dvwc: np.ndarray, depth_cm: int) -> np.ndarray:
    return dvwc * THICK_M[depth_cm] * 1000.0


def main() -> None:
    rl = pl.read_csv(CSV_IN)
    # We DON'T filter on `responded`: ΔVWC of a non-responding event
    # is small but real (~0.001 m³/m³ median), and the captured-water
    # integral should include every event the site saw, not just the
    # ones that passed a per-sensor amplitude threshold.

    fig, axes = plt.subplots(len(POSITIONS), 3, figsize=(15, 11),
                              gridspec_kw=dict(width_ratios=[1.4, 1.1, 1.1]))

    # Pre-compute pivot table for per-event (swale - control) diffs.
    rl_event = rl.select(["event", "sensor_id", "depth_cm", "delta_vwc"])

    for row_i, (label, sw_map, ct_map) in enumerate(POSITIONS):
        # ---- panel (a): ΔVWC distribution per sensor (responding events only) ----
        ax = axes[row_i, 0]
        x = 0
        positions = []
        values = []
        labels = []
        colors = []
        for depth in (10, 40):
            for sid, color in [(ct_map[depth], COLOR_CTRL),
                                 (sw_map[depth], COLOR_SWALE)]:
                v = (rl.filter((pl.col("sensor_id") == sid)
                                  & (pl.col("responded") == True))
                       ["delta_vwc"].drop_nulls().to_numpy())
                positions.append(x); values.append(v)
                labels.append(f"{display(sid)}\n(n={v.size})")
                colors.append(color)
                x += 1
            x += 0.5  # gap between depths

        # boxplot only for non-empty
        non_empty = [i for i, v in enumerate(values) if v.size]
        if non_empty:
            bp = ax.boxplot([values[i] for i in non_empty],
                              positions=[positions[i] for i in non_empty],
                              widths=0.6, showfliers=False, patch_artist=True)
            for patch, i in zip(bp["boxes"], non_empty):
                patch.set_facecolor(colors[i]); patch.set_alpha(0.4)
            for med in bp["medians"]:
                med.set_color("k")
        rng = np.random.default_rng(0)
        for pos, v, c in zip(positions, values, colors):
            if v.size:
                jitter = rng.uniform(-0.18, 0.18, v.size)
                ax.scatter(np.full_like(v, pos) + jitter, v,
                            color=c, s=8, alpha=0.5, edgecolor="none")
        ax.set_xticks(positions)
        ax.set_xticklabels(labels, fontsize=7.5)
        ax.set_ylabel("ΔVWC per event\n(m³/m³)")
        ax.set_title(f"(a) {label} — ΔVWC per responding event",
                      fontsize=10, weight="bold")
        ax.axhline(0, color="grey", linewidth=0.5, linestyle=":")
        ax.grid(alpha=0.25)

        # ---- panel (b): per-event (swale - control) ΔVWC diff ----
        ax = axes[row_i, 1]
        diffs_by_depth = {}
        for depth in (10, 40):
            sw_sid = sw_map[depth]; ct_sid = ct_map[depth]
            sw = (rl_event.filter((pl.col("sensor_id") == sw_sid)
                                     & (pl.col("depth_cm") == depth))
                              .select(["event",
                                        pl.col("delta_vwc").alias("sw")]))
            ct = (rl_event.filter((pl.col("sensor_id") == ct_sid)
                                     & (pl.col("depth_cm") == depth))
                              .select(["event",
                                        pl.col("delta_vwc").alias("ct")]))
            joined = sw.join(ct, on="event", how="inner")
            diffs_by_depth[depth] = (joined["sw"] - joined["ct"]).to_numpy()

        x_pos = [1, 2]
        data = [diffs_by_depth[10], diffs_by_depth[40]]
        bp = ax.boxplot(data, positions=x_pos, widths=0.55,
                          showfliers=False, patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_facecolor("#888"); patch.set_alpha(0.4)
        for med in bp["medians"]:
            med.set_color("k")
        for xi, v in zip(x_pos, data):
            jitter = rng.uniform(-0.12, 0.12, v.size)
            ax.scatter(np.full_like(v, xi) + jitter, v,
                        color="#444", s=8, alpha=0.55, edgecolor="none")
        for xi, v in zip(x_pos, data):
            med = float(np.median(v))
            ax.text(xi, ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] > 0 else 0.1,
                      f"median = {med:+.4f}",
                      ha="center", fontsize=8, weight="bold")
        ax.axhline(0, color="grey", linewidth=0.7)
        ax.set_xticks(x_pos)
        ax.set_xticklabels([f"10 cm\n(n={data[0].size})",
                              f"40 cm\n(n={data[1].size})"], fontsize=8)
        ax.set_ylabel("ΔVWC (swale − control)\n(m³/m³)")
        ax.set_title("(b) Per-event extra wetting at swale",
                      fontsize=10, weight="bold")
        ax.grid(alpha=0.25)

        # ---- panel (c): cumulative mm captured across events ----
        ax = axes[row_i, 2]
        bars = []
        labels_c = []
        colors_c = []
        # Sum of ΔVWC × thickness for each side
        total_sw = 0.0
        total_ct = 0.0
        per_depth = []  # for stacked annotation
        for depth in (10, 40):
            sw_sid = sw_map[depth]; ct_sid = ct_map[depth]
            sw_v = (rl.filter(pl.col("sensor_id") == sw_sid)
                       ["delta_vwc"].drop_nulls().to_numpy())
            ct_v = (rl.filter(pl.col("sensor_id") == ct_sid)
                       ["delta_vwc"].drop_nulls().to_numpy())
            mm_sw = float(vwc_to_mm(sw_v, depth).sum())
            mm_ct = float(vwc_to_mm(ct_v, depth).sum())
            total_sw += mm_sw
            total_ct += mm_ct
            per_depth.append((depth, mm_sw, mm_ct))

        ax.bar([0, 1], [total_ct, total_sw],
                 color=[COLOR_CTRL, COLOR_SWALE], alpha=0.6,
                 edgecolor="black", linewidth=0.5)
        # Stacked breakdown by depth
        bottoms_ct = 0.0; bottoms_sw = 0.0
        depth_alphas = [0.95, 0.55]
        for (depth, mm_sw, mm_ct), alpha in zip(per_depth, depth_alphas):
            ax.bar([0], [mm_ct], bottom=[bottoms_ct], color=COLOR_CTRL,
                     alpha=alpha, edgecolor="black", linewidth=0.4,
                     label=f"{depth} cm" if depth == 10 else None)
            ax.bar([1], [mm_sw], bottom=[bottoms_sw], color=COLOR_SWALE,
                     alpha=alpha, edgecolor="black", linewidth=0.4)
            ax.text(0, bottoms_ct + mm_ct/2, f"{depth} cm\n{mm_ct:.0f} mm",
                      ha="center", va="center", fontsize=8, color="white"
                      if alpha > 0.7 else "black")
            ax.text(1, bottoms_sw + mm_sw/2, f"{depth} cm\n{mm_sw:.0f} mm",
                      ha="center", va="center", fontsize=8, color="white"
                      if alpha > 0.7 else "black")
            bottoms_ct += mm_ct; bottoms_sw += mm_sw
        ax.text(0, total_ct + 5, f"Σ = {total_ct:.0f} mm",
                  ha="center", fontsize=9, weight="bold", color=COLOR_CTRL)
        ax.text(1, total_sw + 5, f"Σ = {total_sw:.0f} mm",
                  ha="center", fontsize=9, weight="bold", color=COLOR_SWALE)
        extra = total_sw - total_ct
        ax.text(0.5, max(total_sw, total_ct) * 1.18,
                  f"extra swale capture = {extra:+.0f} mm "
                  f"({100*extra/total_ct:+.0f} %)",
                  ha="center", fontsize=10, weight="bold",
                  bbox=dict(facecolor="#ffeebb", alpha=0.85, edgecolor="grey"))
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["control", "swale"], fontsize=9)
        ax.set_ylabel("Cumulative captured\nover 94 events (mm)")
        ax.set_title("(c) Total water captured (mm column)",
                      fontsize=10, weight="bold")
        ax.set_ylim(0, max(total_sw, total_ct) * 1.32)
        ax.grid(alpha=0.25, axis="y")

    fig.suptitle("Water captured by the swale vs control — per event "
                  "and cumulative over 94 events",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    out = OUT_DIR / "07j_captured_water.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
