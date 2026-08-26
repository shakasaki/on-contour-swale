"""Quantify event-response amplitude and frequency at 40 cm.

User observation from the per-location 40 cm time series: swale 40 cm
sensors spike higher and have more big-amplitude events than the
control 40 cm sensors.  This script quantifies that — three panels:

  (a) response rate per sensor (fraction of the 94 events the sensor
      responded to, using the rising-limb detector's `responded` flag);
  (b) peak rise per event per sensor (strip + box) — shows that
      swale-side spikes go much higher than control;
  (c) count of "big" events per sensor at two amplitude thresholds
      (ΔVWC > 0.02 and > 0.05) — quantifies the "many more big
      events" observation.

Sensors are ordered by slope position (Top → Mid/Mound → Bottom).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from swale.display_names import display

CSV_IN = Path("plots/05_rising_limb_metrics.csv")
OUT = Path("plots/07e_event_amplitude_40cm.png")

# (sensor_id, treatment, slope-position label) at 40 cm, ordered by
# the slope (control + swale side-by-side at each position).
ORDER_40 = [
    ("SMS12", "control", "Top"),
    ("SMS02", "swale",   "Top (SwB)"),
    ("SMS14", "control", "Mid"),
    ("SMS05", "swale",   "Mound (SwD)"),
    ("SMS10", "swale",   "Step"),
    ("SMS16", "control", "Bottom"),
    ("SMS07", "swale",   "Bot 1 (SwE)"),
    ("SMS09", "swale",   "Bot 2 (SwF)"),
]

PALETTE = {"control": "#d62728", "swale": "#1f77b4"}


def main() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    rl = pl.read_csv(CSV_IN).filter(pl.col("depth_cm") == 40)
    n_events = rl["event"].n_unique()

    fig, axes = plt.subplots(3, 1, figsize=(10, 9))

    # ---- panel (a) response rate ----
    ax = axes[0]
    rates = []
    labels = []
    colors = []
    for sid, treat, pos in ORDER_40:
        sub = rl.filter(pl.col("sensor_id") == sid)
        rate = 100 * float(sub["responded"].sum()) / float(sub.height) if sub.height else 0
        rates.append(rate)
        labels.append(f"{display(sid)}\n{pos}")
        colors.append(PALETTE[treat])
    x = np.arange(len(ORDER_40))
    ax.bar(x, rates, color=colors, alpha=0.7, edgecolor="black", linewidth=0.5)
    for xi, r in zip(x, rates):
        ax.text(xi, r + 1, f"{r:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Response rate (% of events)")
    ax.set_title(f"(a) Fraction of {n_events} events with detectable response at 40 cm",
                  fontsize=10, weight="bold")
    ax.set_ylim(0, 65)

    # ---- panel (b) peak ΔVWC distribution per sensor ----
    ax = axes[1]
    rng = np.random.default_rng(0)
    box_data = []
    for sid, treat, pos in ORDER_40:
        v = (rl.filter((pl.col("sensor_id") == sid)
                         & (pl.col("responded") == True))
                ["delta_vwc"].drop_nulls().to_numpy())
        v = v[np.isfinite(v)]
        box_data.append(v)
    bp = ax.boxplot(box_data, positions=x, widths=0.6, showfliers=False,
                     patch_artist=True)
    for patch, (_, treat, _) in zip(bp["boxes"], ORDER_40):
        patch.set_facecolor(PALETTE[treat])
        patch.set_alpha(0.4)
    for med in bp["medians"]:
        med.set_color("k")
    for xi, v, (_, treat, _) in zip(x, box_data, ORDER_40):
        if v.size:
            jitter = rng.uniform(-0.18, 0.18, v.size)
            ax.scatter(np.full_like(v, xi) + jitter, v,
                        color=PALETTE[treat], s=10, alpha=0.6, edgecolor="none")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Per-event ΔVWC (m³/m³)")
    ax.set_title("(b) Per-event amplitude — every responded event "
                  "(outliers shown)", fontsize=10, weight="bold")
    ax.axhline(0.05, color="grey", linestyle=":", linewidth=0.7)
    ax.axhline(0.02, color="grey", linestyle=":", linewidth=0.7)
    ax.text(len(ORDER_40)-0.5, 0.052, "ΔVWC = 0.05", fontsize=7,
              color="grey", ha="right")
    ax.text(len(ORDER_40)-0.5, 0.022, "ΔVWC = 0.02", fontsize=7,
              color="grey", ha="right")

    # ---- panel (c) count of "big" events per sensor ----
    ax = axes[2]
    n_above_2 = []
    n_above_5 = []
    for sid, _, _ in ORDER_40:
        sub = rl.filter(pl.col("sensor_id") == sid)
        n_above_2.append(int((sub["delta_vwc"] > 0.02).sum()))
        n_above_5.append(int((sub["delta_vwc"] > 0.05).sum()))
    width = 0.4
    ax.bar(x - width/2, n_above_2, width, color="lightgrey",
            edgecolor="black", linewidth=0.5, label="ΔVWC > 0.02")
    ax.bar(x + width/2, n_above_5, width, color="dimgrey",
            edgecolor="black", linewidth=0.5, label="ΔVWC > 0.05")
    for xi, n in zip(x, n_above_2):
        ax.text(xi - width/2, n + 0.3, str(n), ha="center", fontsize=7)
    for xi, n in zip(x, n_above_5):
        ax.text(xi + width/2, n + 0.3, str(n), ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Number of events")
    ax.set_title(f"(c) Count of large-amplitude events at 40 cm "
                  f"(out of {n_events})", fontsize=10, weight="bold")
    ax.legend(loc="upper right", fontsize=8)

    fig.suptitle("40 cm event response — counts & amplitudes per sensor",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
