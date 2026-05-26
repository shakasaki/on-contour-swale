"""Annualise the swale vs control captured-water budget.

Takes the per-event ΔVWC captured-water totals from
`05_rising_limb_metrics.csv`, converts to column-equivalent mm using
the same layer-thickness model as `07j_captured_water.py` (10 cm
sensor → 0.25 m layer; 40 cm sensor → 0.40 m layer), and annualises
by the record span.

Every step is shown numerically in the figure so a reader can audit
the arithmetic.

Inputs and constants
--------------------
    record_start    first detected event = 2024-06-04
    record_end      last detected event  = 2026-01-25
    record_days     (end − start)
    record_years    record_days / 365.25
    n_events        94 (the detector output)
    events_per_year n_events / record_years     ≈ 57.1 / yr
    THICK           10 cm → 0.25 m,  40 cm → 0.40 m layers

Per slope position, per event, per sensor:
    captured_mm     = ΔVWC (m³/m³) · layer_thickness (m) · 1000
                      → mm of water depth in that layer.
Cumulative over the 94 events, then divided by record_years to get
mm/yr per m² of soil strip.

Annualised excess captured by the swale at each slope position:
    excess_mm_per_yr_per_m2 = (Σ_swale − Σ_control) / record_years

Multiplied by an effective strip area to get liters/year. The
default `AREA_M2 = 50` is a transparent placeholder — adjust to your
estimate of the swale catchment per slope-position strip. We also
print the numbers for 10 m², 50 m², 200 m² so the sensitivity to
this choice is visible.

Caveat
------
The "extra" water at the Mid/Bottom positions is **redistributed**
from the Top (which captures less than its control twin), not net
new water. The swale is a routing device, not a rainfall augmenter.
What the per-position liters mean: "extra water available at the
trees rooted in the Mound / Bottom strips because the swale is
there, vs the same strip on an un-swaled slope."
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from swale.display_names import display

CSV_EVENTS = Path("plots/00_events_from_soil.csv")
CSV_RL     = Path("plots/05_rising_limb_metrics.csv")
OUT_PNG    = Path("plots/07k_annual_water_budget.png")
OUT_CSV    = Path("plots/07k_annual_water_budget.csv")

THICK_M = {10: 0.25, 40: 0.40}

POSITIONS = [
    ("Top",        {10: "SMS01", 40: "SMS02"}, {10: "SMS11", 40: "SMS12"}),
    ("Mid/Mound",  {10: "SMS04", 40: "SMS05"}, {10: "SMS13", 40: "SMS14"}),
    ("Bottom 1",   {10: "SMS06", 40: "SMS07"}, {10: "SMS15", 40: "SMS16"}),
    ("Bottom 2",   {10: "SMS08", 40: "SMS09"}, {10: "SMS15", 40: "SMS16"}),
]

# Area scenarios for the L/yr table at the bottom of the figure.
AREA_SCENARIOS_M2 = [10, 50, 200]
AREA_DEFAULT_M2 = 50

COLOR_SWALE = "#1f77b4"
COLOR_CTRL  = "#d62728"


def captured_mm_per_position(rl: pl.DataFrame, depth: int,
                              swale_id: str, control_id: str
                              ) -> tuple[float, float]:
    sw = float((rl.filter(pl.col("sensor_id") == swale_id)
                   ["delta_vwc"]).sum())
    ct = float((rl.filter(pl.col("sensor_id") == control_id)
                   ["delta_vwc"]).sum())
    return sw * THICK_M[depth] * 1000.0, ct * THICK_M[depth] * 1000.0


def main() -> None:
    # ---- time base ----
    events = pl.read_csv(CSV_EVENTS).with_columns(
        pl.col("start").str.to_datetime().alias("start_dt"),
    )
    record_start = events["start_dt"].min()
    record_end = events["start_dt"].max()
    span_days = (record_end - record_start).total_seconds() / 86400
    record_years = span_days / 365.25
    n_events = events.height
    events_per_year = n_events / record_years

    # ---- captured-water totals ----
    rl = pl.read_csv(CSV_RL)  # include all events (responded or not)

    rows = []
    for label, sw, ct in POSITIONS:
        sw10_mm, ct10_mm = captured_mm_per_position(rl, 10, sw[10], ct[10])
        sw40_mm, ct40_mm = captured_mm_per_position(rl, 40, sw[40], ct[40])
        sw_total = sw10_mm + sw40_mm
        ct_total = ct10_mm + ct40_mm
        rows.append({
            "position":         label,
            "swale_total_mm":   sw_total,
            "control_total_mm": ct_total,
            "swale_per_year_mm_m2":   sw_total / record_years,
            "control_per_year_mm_m2": ct_total / record_years,
            "extra_per_year_mm_m2":   (sw_total - ct_total) / record_years,
            "extra_L_per_year_per_m2": (sw_total - ct_total) / record_years,
        })

    summary = pl.DataFrame(rows)
    summary.write_csv(OUT_CSV)
    print(f"wrote {OUT_CSV}")
    print(summary)

    # ---- figure ----
    fig = plt.figure(figsize=(13, 9))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.1])
    ax_bar = fig.add_subplot(gs[0])
    ax_tab = fig.add_subplot(gs[1])
    ax_tab.axis("off")

    # Bar: mm/yr/m² per position, swale vs control side-by-side
    pos_labels = [r["position"] for r in rows]
    x = np.arange(len(pos_labels))
    width = 0.36
    ct_yr = [r["control_per_year_mm_m2"] for r in rows]
    sw_yr = [r["swale_per_year_mm_m2"] for r in rows]
    extras = [r["extra_per_year_mm_m2"] for r in rows]
    ax_bar.bar(x - width/2, ct_yr, width, color=COLOR_CTRL, alpha=0.7,
                 edgecolor="black", linewidth=0.5, label="control")
    ax_bar.bar(x + width/2, sw_yr, width, color=COLOR_SWALE, alpha=0.7,
                 edgecolor="black", linewidth=0.5, label="swale")
    # Annotate extras (above the higher of the two bars)
    for xi, (c, s, ex) in enumerate(zip(ct_yr, sw_yr, extras)):
        top = max(c, s)
        ax_bar.text(xi, top + 30,
                     f"Δ = {ex:+.0f} mm/yr/m²\n"
                     f"({100*ex/c:+.0f} %)",
                     ha="center", va="bottom", fontsize=9,
                     weight="bold",
                     color=("#1a7e1a" if ex > 0 else "#a51d1d"),
                     bbox=dict(facecolor="white", alpha=0.85,
                                edgecolor="grey", linewidth=0.4))
    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels(pos_labels)
    ax_bar.set_ylabel("Captured water (mm / yr per m² of strip)")
    ax_bar.set_title(
        f"Annualised captured water — swale vs control by slope position\n"
        f"(period {record_start.date()} → {record_end.date()}; "
        f"{n_events} events / {record_years:.2f} yr = "
        f"{events_per_year:.1f} events/yr)",
        fontsize=11, weight="bold")
    ax_bar.legend(loc="upper left", fontsize=9)
    ax_bar.grid(alpha=0.25, axis="y")
    ax_bar.set_ylim(0, max(max(ct_yr), max(sw_yr)) * 1.40)

    # Table: site-scale projection (L/yr) at three area scenarios
    header = ["Position",
                "Control\n(mm/yr/m²)",
                "Swale\n(mm/yr/m²)",
                "Extra Δ\n(mm/yr/m²)",
                f"Extra Δ at\n10 m² (L/yr)",
                f"Extra Δ at\n50 m² (L/yr)",
                f"Extra Δ at\n200 m² (L/yr)"]
    cells = []
    for r in rows:
        cells.append([
            r["position"],
            f"{r['control_per_year_mm_m2']:.0f}",
            f"{r['swale_per_year_mm_m2']:.0f}",
            f"{r['extra_per_year_mm_m2']:+.0f}",
            f"{r['extra_per_year_mm_m2'] * 10:+,.0f}",
            f"{r['extra_per_year_mm_m2'] * 50:+,.0f}",
            f"{r['extra_per_year_mm_m2'] * 200:+,.0f}",
        ])
    # Whole-swale row: sum across downslope positions only (since Top
    # is the source). Use Mound + Bot1 + Bot2 as the active sink.
    sink_rows = [r for r in rows
                  if r["position"] in ("Mid/Mound", "Bottom 1", "Bottom 2")]
    sink_extra = sum(r["extra_per_year_mm_m2"] for r in sink_rows)
    cells.append([
        "→ Mid+Bot1+Bot2 sink (sum)",
        "—", "—",
        f"{sink_extra:+.0f}",
        f"{sink_extra * 10:+,.0f}",
        f"{sink_extra * 50:+,.0f}",
        f"{sink_extra * 200:+,.0f}",
    ])

    table = ax_tab.table(cellText=cells, colLabels=header,
                          loc="upper center", cellLoc="center",
                          colWidths=[0.16, 0.13, 0.13, 0.13, 0.14, 0.14, 0.14])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.55)
    # Highlight extra columns
    for j in range(3, 7):
        for i in range(1, len(cells) + 1):
            cell = table[(i, j)]
            try:
                val = float(cells[i-1][j].replace(",", "").replace("+", "")
                              .replace("−", "-"))
                if val > 0:
                    cell.set_facecolor("#e8f5e9")
                elif val < 0:
                    cell.set_facecolor("#ffebee")
            except ValueError:
                pass
    # Bold the sink row
    for j in range(7):
        table[(len(cells), j)].set_text_props(weight="bold")

    ax_tab.text(0.0, 0.05,
                  "Assumptions:\n"
                  f"• Layer-thickness conversion: ΔVWC(10cm)·0.25 m·1000 + ΔVWC(40cm)·0.40 m·1000 → mm of column water at peak.\n"
                  "• Annualisation: total over 94 events ÷ 1.645 yr.\n"
                  "• L/yr columns project the mm/yr/m² rate onto a hypothetical 10/50/200 m² strip per slope position.\n"
                  "• Extra water at downslope positions is REDISTRIBUTED from the Top (Δ = −660 mm/yr/m² at Top), not net new water.",
                  transform=ax_tab.transAxes,
                  fontsize=8.5, family="monospace", va="bottom",
                  color="#444")

    fig.suptitle("Annualised water budget — what the swale captures per "
                  "year per square metre of strip",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(OUT_PNG, dpi=130)
    plt.close(fig)
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
