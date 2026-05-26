"""Recession τ distributions, split by slope position.

Reads ``plots/07_recession_fits.csv`` (produced by 07_recession_fits.py)
and produces three figures — Top slope, Mid/Mound, Bottom slope — each
comparing the exponential τ distribution at the matched swale + control
sensors for that position, separately at 10 cm and 40 cm.

Pooling all swale vs all control hides the spatial gradient (the
Mound, Step, and Bottom-slope sensors of the swale do not drain on
the same time scale); these per-position figures keep the comparison
fair.

Filters match the per-location τ map (07 → 11 pipeline):
    R² ≥ 0.7
    τ ∈ [5, 500] h
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from swale.display_names import display

CSV_IN = Path("plots/07_recession_fits.csv")
OUT_DIR = Path("plots")

R2_MIN = 0.7
TAU_MIN_H, TAU_MAX_H = 5.0, 500.0

# Slope-paired groupings.  (control_sensors, swale_sensors).
# SMS10 (Step) has no obvious control analog — listed in the doc but
# excluded from these three position figures.
GROUPS: dict[str, dict[str, list[str]]] = {
    "top":    {"control": ["SMS11", "SMS12"], "swale": ["SMS01", "SMS02"]},
    "mid":    {"control": ["SMS13", "SMS14"], "swale": ["SMS04", "SMS05"]},
    "bottom": {"control": ["SMS15", "SMS16"],
                "swale":   ["SMS06", "SMS07", "SMS08", "SMS09"]},
}

GROUP_TITLES = {
    "top":    "Top slope — cn_t_* (control) vs sw_t_* (swale)",
    "mid":    "Mid / Mound — cn_m_* (control) vs sw_m_* (swale)",
    "bottom": "Bottom slope — cn_b_* (control) vs sw_b1_*, sw_b2_* (swale)",
}

PALETTE = {"control": "#d62728", "swale": "#1f77b4"}
DEPTHS = [10, 40]


def load_clean() -> pl.DataFrame:
    df = pl.read_csv(CSV_IN)
    return df.filter(
        (pl.col("exp_r2") >= R2_MIN)
        & (pl.col("exp_tau_h") >= TAU_MIN_H)
        & (pl.col("exp_tau_h") <= TAU_MAX_H)
    )


def plot_one_group(fits: pl.DataFrame, group_key: str, ymax: float) -> Path:
    spec = GROUPS[group_key]
    sensors_all = spec["control"] + spec["swale"]

    sub = fits.filter(pl.col("sensor_id").is_in(sensors_all))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, depth in zip(axes, DEPTHS):
        # Collect per-sensor τ at this depth, in display order:
        # control sensors (red) then swale sensors (blue).
        positions = []
        values: list[np.ndarray] = []
        labels: list[str] = []
        colors: list[str] = []
        x = 1
        for treat in ("control", "swale"):
            for sid in spec[treat]:
                v = (sub.filter(
                        (pl.col("sensor_id") == sid)
                        & (pl.col("depth_cm") == depth))
                     ["exp_tau_h"].drop_nulls().to_numpy())
                v = v[np.isfinite(v)]
                positions.append(x)
                values.append(v)
                labels.append(f"{display(sid)}\n(n={v.size})")
                colors.append(PALETTE[treat])
                x += 1

        # Boxes only for sensors with data; we still want to keep the
        # x-axis slot so the figure reads consistently.
        non_empty_idx = [i for i, v in enumerate(values) if v.size]
        if non_empty_idx:
            bp = ax.boxplot(
                [values[i] for i in non_empty_idx],
                positions=[positions[i] for i in non_empty_idx],
                widths=0.6, showfliers=False, patch_artist=True,
            )
            for patch, i in zip(bp["boxes"], non_empty_idx):
                patch.set_facecolor(colors[i])
                patch.set_alpha(0.45)
            for med in bp["medians"]:
                med.set_color("k")

        rng = np.random.default_rng(0)
        for pos, v, c in zip(positions, values, colors):
            if v.size:
                jitter = rng.uniform(-0.15, 0.15, v.size)
                ax.scatter(np.full_like(v, pos) + jitter, v,
                            color=c, s=10, alpha=0.7, edgecolor="none")

        ax.set_xticks(positions)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(0, ymax)
        ax.set_title(f"{depth} cm", fontsize=11, weight="bold")
        ax.axvline(len(spec["control"]) + 0.5, color="grey",
                    linestyle=":", linewidth=0.8)
        if depth == 10:
            ax.set_ylabel("Exp. recession τ (h)")

    fig.suptitle(GROUP_TITLES[group_key], fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = OUT_DIR / f"07c_tau_by_slope_{group_key}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def main() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    fits = load_clean()
    # Common y-axis range so the three figures are directly comparable.
    ymax = float(fits["exp_tau_h"].max()) * 1.05
    for key in GROUPS:
        out = plot_one_group(fits, key, ymax)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
