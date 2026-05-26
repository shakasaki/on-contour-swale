"""Plan-view map of the soil-moisture sensor pairs.

Reads ``data/SMS_locations.csv`` via ``swale.sites`` (which already
returns coords in the canonical frame: +X=East, +Y=North) and plots
all SMS pairs colour-coded by treatment and labelled by Widmer-thesis
location (Top slope / Mound / Step / Bottom slope 1+2 for the swale;
Top / Mid / Bottom slope for the control). Z is encoded as marker
fill colour so the slope direction shows visually.

Outputs:
    plots/09_sensor_layout.png

Run from project root::

    PYTHONPATH=src .venv/bin/python scripts/09_sensor_layout.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse

from swale.config import load_settings
from swale.sites import sensor_pairs

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
LOCATIONS_CSV = ROOT / "data" / "SMS_locations.csv"
OUT_PNG = ROOT / "plots" / "09_sensor_layout.png"

# Visual tunables
MARKER_SIZE = 220                    # base scatter marker size
STD_ELLIPSE_NSIGMA = 2.0             # uncertainty-ellipse half-axis in std units

# Per-location label offsets in PIXEL units (immune to axis inversion).
# Swale labels (left side of figure) push to the right; control labels
# (right side of figure) push to the left. Vertical staggers avoid the
# Step/Mound collision.
LABEL_OFFSETS_PIXELS: dict[tuple[str, ...], tuple[float, float]] = {
    ("SMS01", "SMS02"):           ( 55,  -5),   # Top slope swale
    ("SMS03", "SMS04", "SMS05"):  ( 55, -25),   # Mound (above Step on screen)
    ("SMS10",):                   ( 55,  25),   # Step (below Mound on screen)
    # SMS 06,07 sits visibly offset from the main swale axis (X=4.19 vs
    # X≈5 for the others); push its label well to the right so it
    # doesn't collide with SMS 08,09.
    ("SMS06", "SMS07"):           (140,   0),   # Bottom slope 1
    ("SMS08", "SMS09"):           ( 55,  25),   # Bottom slope 2
    ("SMS11", "SMS12"):           (-55,  -5),   # Control Top slope
    ("SMS13", "SMS14"):           (-55,  -5),
    ("SMS15", "SMS16"):           (-55,  -5),
}
DEFAULT_LABEL_OFFSET_PIXELS = (55, -5)


def plot_layout(out: Path) -> None:
    pairs = sensor_pairs(LOCATIONS_CSV)
    if not pairs:
        raise RuntimeError(f"no SMS pairs parsed from {LOCATIONS_CSV}")

    fig, ax = plt.subplots(figsize=(9, 9))

    xs = np.array([p.x for p in pairs])
    ys = np.array([p.y for p in pairs])
    zs = np.array([p.z for p in pairs])

    swale_color = SETTINGS.treatment_colors.get("swale", "#1f77b4")
    control_color = SETTINGS.treatment_colors.get("control", "#d62728")

    # Z heatmap (a single shared colorbar across treatments)
    sc = ax.scatter(
        xs, ys, c=zs, cmap="viridis",
        s=MARKER_SIZE, edgecolors="black", linewidths=1.2, zorder=4,
    )

    # Treatment-coloured outline ring around each marker
    for p in pairs:
        ring = "o" if p.treatment == "swale" else "s"
        ax.scatter([p.x], [p.y], marker=ring, s=MARKER_SIZE * 1.7,
                   facecolors="none",
                   edgecolors=swale_color if p.treatment == "swale" else control_color,
                   linewidths=2.0, zorder=3)

        # Uncertainty ellipse (SMS 10 is the only one that's visibly large)
        if p.x_std > 0.05 or p.y_std > 0.05:
            ell = Ellipse(
                (p.x, p.y),
                width=2.0 * STD_ELLIPSE_NSIGMA * p.x_std,
                height=2.0 * STD_ELLIPSE_NSIGMA * p.y_std,
                angle=0.0,
                facecolor="none", edgecolor="black", linestyle="--",
                linewidth=0.8, alpha=0.5, zorder=2,
            )
            ax.add_patch(ell)

        # Text label: display names + Widmer location + Z
        from swale.display_names import display
        disp = " · ".join(display(sid) for sid in p.sensor_ids)
        label = f"{disp}\n{p.widmer_location}\nZ={p.z:+.2f}"
        dx_px, dy_px = LABEL_OFFSETS_PIXELS.get(p.sensor_ids, DEFAULT_LABEL_OFFSET_PIXELS)
        ha = "left" if dx_px >= 0 else "right"
        ax.annotate(
            label, xy=(p.x, p.y),
            xytext=(dx_px, dy_px), textcoords="offset points",
            fontsize=8.5, ha=ha, va="center",
            bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "lightgrey",
                  "boxstyle": "round,pad=0.25"},
            arrowprops={"arrowstyle": "-", "color": "grey", "alpha": 0.5, "lw": 0.6},
            zorder=5,
        )

    # Slope-axis hint: draw thin arrows from top-slope to bottom-slope per side.
    for treatment, color in (("swale", swale_color), ("control", control_color)):
        side = [p for p in pairs if p.treatment == treatment]
        side.sort(key=lambda p: p.y)
        if len(side) >= 2:
            ax.annotate(
                "", xy=(side[-1].x, side[-1].y), xytext=(side[0].x, side[0].y),
                arrowprops={"arrowstyle": "->", "color": color, "alpha": 0.25,
                            "lw": 2.5, "shrinkA": 18, "shrinkB": 18},
                zorder=1,
            )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cbar.set_label("Z (m, elevation in local frame; up positive)")

    # Treatment legend
    swale_proxy = plt.Line2D([0], [0], marker="o", color="none",
                              markeredgecolor=swale_color, markerfacecolor="lightgrey",
                              markersize=12, markeredgewidth=2, label="Swale")
    control_proxy = plt.Line2D([0], [0], marker="s", color="none",
                                markeredgecolor=control_color, markerfacecolor="lightgrey",
                                markersize=12, markeredgewidth=2, label="Control")
    unc_proxy = plt.Line2D([0], [0], linestyle="--", color="black",
                            label=f"{STD_ELLIPSE_NSIGMA}σ uncertainty (sw_s_40)")
    ax.legend(handles=[swale_proxy, control_proxy, unc_proxy],
              loc="upper left", fontsize=10, frameon=True)

    ax.set_xlabel("X (m, canonical frame; +X = East)")
    ax.set_ylabel("Y (m, canonical frame; +Y = North)")
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)

    # Tight axis limits — labels live in pixel space and don't need padding.
    ax.set_xlim(xs.min() - 0.8, xs.max() + 0.8)
    ax.set_ylim(ys.min() - 0.8, ys.max() + 0.8)

    ax.set_title(
        "TEROS-12 sensor pair locations — plan view\n"
        "5 swale pairs + 3 control triples; Z encoded as fill colour. "
        "Coord frame: data/SMS_locations.csv",
        fontsize=11,
    )

    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  wrote {out.relative_to(ROOT)}")


def main() -> None:
    OUT_PNG.parent.mkdir(exist_ok=True)
    plot_layout(OUT_PNG)


if __name__ == "__main__":
    main()
