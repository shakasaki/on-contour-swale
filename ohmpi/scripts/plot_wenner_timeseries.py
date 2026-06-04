"""Weekly distribution of Wenner apparent resistivity per line, over the campaign,
with daily precipitation on a shared time axis.

Five stacked panels sharing the date axis:
    precip (daily bars; gauge-fault window after RAIN_CUTOFF greyed)
    line A / B / C / D : one violin per ISO week of all earth-quad rho_a values

Earth quads only (test-circuit pair excluded), known-bad calibration days
dropped. The per-quad `keep` flag is NOT applied: Wenner reciprocals are clean
(~93 % pass) and the intent here is to see the full spread, not the QC subset.

    conda activate swale
    python ohmpi/scripts/plot_wenner_timeseries.py
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

from swale.config import load_settings
from swale.loader import load_swale_dataset

R_TABLE = REPO / "ohmpi" / "cache" / "r_table.parquet"
OUT_DIR = REPO / "ohmpi" / "plots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LINES = ["A", "B", "C", "D"]
TEST_CIRCUIT = ["60_61_62_64", "62_64_60_61"]
LINE_COLOR = {"A": "#1b9e77", "B": "#d95f02", "C": "#7570b3", "D": "#e7298a"}
# Nearest 40 cm VWC sensor per Wenner line, from electrode↔sensor coords in the
# shared rot180 frame (min distance over each line's electrodes). A & D are both
# closest to the Mound station (SMS05) — that is the real geometry, not a bug;
# line A is a near-tie with Bottom-2 (SMS09), so it under-represents that line.
LINE_SMS = {"A": ["SMS05"], "B": ["SMS02"], "C": ["SMS10"], "D": ["SMS05"]}


def wenner_rho() -> pl.DataFrame:
    """Kept earth-quad Wenner rho_a, bad days + test circuit removed, tagged by ISO week."""
    r = pl.read_parquet(R_TABLE)
    return (
        r.filter(
            (pl.col("array") == "wenner")
            & pl.col("keep")                         # QC: drop noisy quads (A/B)
            & ~pl.col("drop_day")
            & ~pl.col("quad").is_in(TEST_CIRCUIT)
            & pl.col("rho_a").is_not_null()
            & pl.col("line").is_in(LINES)
        )
        .with_columns(pl.col("timestamp").dt.truncate("1w").dt.date().alias("week"))
        .select(["line", "week", "rho_a"])
    )


def daily_vwc() -> pl.DataFrame:
    """Daily-mean 40 cm VWC per Wenner line (mean over that line's sensors)."""
    cfg = load_settings()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(cfg.data_root, cfg.metadata_xlsx, grid="none")
    sms = (
        df.filter((pl.col("variable") == "moisture") & (pl.col("depth_cm") == 40))
        .with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("sensor_id", "day").agg(vwc=pl.col("value").mean())
    )
    out = []
    for line, ids in LINE_SMS.items():
        d = (sms.filter(pl.col("sensor_id").is_in(ids))
             .group_by("day").agg(vwc=pl.col("vwc").mean())
             .with_columns(pl.lit(line).alias("line")).sort("day"))
        out.append(d)
    return pl.concat(out)


def main() -> None:
    rho = wenner_rho()
    vwc = daily_vwc()

    # x-range = OhmPi campaign span
    x0 = rho["week"].min()
    x1 = rho["week"].max() + timedelta(days=7)
    vwc = vwc.filter((pl.col("day") >= x0) & (pl.col("day") <= x1))

    # shared y-range across lines (kept quads only; clean spread)
    RHO_YLIM = (2.0, 12.0)

    fig, axes = plt.subplots(
        5, 1, figsize=(15, 11), sharex=True,
        gridspec_kw={"height_ratios": [1.1, 1, 1, 1, 1], "hspace": 0.12},
    )

    # ── 40 cm VWC per line (slope position) ──
    ax_v = axes[0]
    for line in LINES:
        d = vwc.filter(pl.col("line") == line).sort("day")
        ax_v.plot(mdates.date2num(d["day"].to_list()), d["vwc"].to_numpy(),
                  color=LINE_COLOR[line], lw=1.2, label=f"line {line}")
    ax_v.set_ylabel("40 cm VWC\n[m³/m³]")
    ax_v.legend(ncol=4, fontsize=8, loc="upper right")
    ax_v.grid(alpha=0.3)
    ax_v.set_title("Wenner apparent resistivity per line (weekly distribution, kept "
                   "quads) with 40 cm soil moisture", fontsize=12)

    # ── one violin panel per line ──
    for ax, line in zip(axes[1:], LINES):
        d = rho.filter(pl.col("line") == line)
        weeks = sorted(d["week"].unique().to_list())
        data, pos = [], []
        for wk in weeks:
            vals = d.filter(pl.col("week") == wk)["rho_a"].to_numpy()
            if vals.size >= 3:                       # need a few points for a violin
                data.append(vals)
                pos.append(mdates.date2num(wk + timedelta(days=3)))  # week centre
        if data:
            vp = ax.violinplot(data, positions=pos, widths=5.0,
                               showmedians=True, showextrema=False)
            for body in vp["bodies"]:
                body.set_facecolor(LINE_COLOR[line])
                body.set_alpha(0.6)
            vp["cmedians"].set_color("black")
            vp["cmedians"].set_linewidth(0.8)
        ax.set_ylabel(f"line {line}\nρₐ [Ω·m]")
        ax.set_ylim(*RHO_YLIM)
        ax.grid(axis="y", alpha=0.3)

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].set_xlim(mdates.date2num(x0), mdates.date2num(x1))
    axes[-1].set_xlabel("date")

    out = OUT_DIR / "wenner_rho_timeseries.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
    print(f"weeks per line: " + ", ".join(
        f"{l}={rho.filter(pl.col('line')==l)['week'].n_unique()}" for l in LINES))


if __name__ == "__main__":
    main()
