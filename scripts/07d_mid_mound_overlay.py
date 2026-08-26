"""Overlay swale Mound vs control Mid VWC time series.

The user expectation is that the Mound (SMS04 / SMS05, just downslope
of the swale trench) should retain noticeably more water than the
control mid-slope sensors (SMS13 / SMS14) at both 10 cm and 40 cm.

This script overlays the actual time series so the visual answer is
unambiguous.  No new processing — just reads the cache and plots.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl

from swale.display_names import display

OUT = Path("plots/07d_mid_mound_overlay.png")

PAIRS = [
    # (depth_cm, swale_sensor, control_sensor)
    (10, "SMS04", "SMS13"),
    (40, "SMS05", "SMS14"),
]


def load_moisture() -> pl.DataFrame:
    files = sorted(Path("cache").glob("logger=*.parquet"))
    df = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    df = df.filter((pl.col("variable") == "moisture")
                    & (pl.col("sensor_type") == "TEROS12")
                    & (pl.col("value") > 0.01))
    first = (df.group_by("sensor_id")
               .agg(pl.col("timestamp").min().alias("first")))
    return (df.join(first, on="sensor_id")
              .filter(pl.col("timestamp")
                       >= pl.col("first") + pl.duration(days=14)))


def main() -> None:
    df = load_moisture()
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)

    for ax, (depth, swale_id, ctrl_id) in zip(axes, PAIRS):
        for sid, color, label_treat in [
            (ctrl_id,  "#d62728", f"control mid ({display(ctrl_id)})"),
            (swale_id, "#1f77b4", f"swale Mound ({display(swale_id)})"),
        ]:
            s = (df.filter(pl.col("sensor_id") == sid).sort("timestamp"))
            ax.plot(s["timestamp"].to_numpy(), s["value"].to_numpy(),
                     color=color, linewidth=0.7, label=label_treat)
            mean = float(s["value"].mean())
            ax.axhline(mean, color=color, linestyle="--", linewidth=0.8,
                         alpha=0.7)
            ax.text(0.005, 0.02 + (0.08 if sid == swale_id else 0.0),
                     f"{label_treat} mean = {mean:.3f}",
                     transform=ax.transAxes, fontsize=8,
                     color=color, va="bottom")
        ax.set_ylabel(f"VWC at {depth} cm (m³/m³)")
        ax.set_title(f"{depth} cm — Mound vs control Mid",
                      fontsize=10, weight="bold")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)

    axes[-1].set_xlabel("Date")
    fig.suptitle("Mid / Mound: swale sw_m_10 + sw_m_40 (Mound) vs control "
                  "cn_m_10 + cn_m_40 (Mid)", fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
