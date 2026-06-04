"""Daily Wenner apparent resistivity per line over the campaign.

One panel per line (A–D); each shows the daily median rho_a (line) with the
daily inter-quartile band (25–75 %) shaded. Built from kept earth quads only
(test-circuit pair + known-bad days removed). 245 survey days, 12–21 kept quad
measurements per line per day — enough for a robust daily median/IQR.

Each panel also carries, on a twin axis, the 40 cm VWC of that line's nearest
sensor (A/D=Mound/SMS05, B=Top/SMS02, C=Step/SMS10; nearest-station mapping from
the shared rot180 coords). Lines are slope-crossing transects, so this single
sensor only represents the closest point of the line — A & D share SMS05.

    conda activate swale
    python ohmpi/scripts/plot_wenner_daily.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

from swale.config import load_settings
from swale.loader import load_swale_dataset

R_TABLE = REPO / "ohmpi" / "cache" / "r_table.parquet"
OUT_DIR = REPO / "ohmpi" / "plots"

LINES = ["A", "B", "C", "D"]
TEST_CIRCUIT = ["60_61_62_64", "62_64_60_61"]
LINE_COLOR = {"A": "#1b9e77", "B": "#d95f02", "C": "#7570b3", "D": "#e7298a"}
RHO_YLIM = (2.0, 12.0)
VWC_COLOR = "#444444"
# nearest 40 cm VWC sensor per line (see plot_wenner_timeseries.py); A & D = Mound
LINE_SMS = {"A": "SMS05", "B": "SMS02", "C": "SMS10", "D": "SMS05"}
LINE_POS = {"A": "Mound", "B": "Top", "C": "Step", "D": "Mound"}


def daily_stats() -> pl.DataFrame:
    """Per (line, day): median rho_a + 25/75 quantiles over kept earth quads."""
    r = pl.read_parquet(R_TABLE)
    return (
        r.filter(
            (pl.col("array") == "wenner")
            & pl.col("keep")
            & ~pl.col("drop_day")
            & ~pl.col("quad").is_in(TEST_CIRCUIT)
            & pl.col("rho_a").is_not_null()
            & pl.col("line").is_in(LINES)
        )
        .group_by("line", "day")
        .agg(
            med=pl.col("rho_a").median(),
            q25=pl.col("rho_a").quantile(0.25),
            q75=pl.col("rho_a").quantile(0.75),
            n=pl.len(),
        )
        .sort("line", "day")
    )


def daily_vwc() -> pl.DataFrame:
    """Daily-mean 40 cm VWC for every sensor used by a line."""
    cfg = load_settings()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(cfg.data_root, cfg.metadata_xlsx, grid="none")
    return (
        df.filter((pl.col("variable") == "moisture") & (pl.col("depth_cm") == 40)
                  & pl.col("sensor_id").is_in(list(set(LINE_SMS.values()))))
        .with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by("sensor_id", "day").agg(vwc=pl.col("value").mean())
    )


def main() -> None:
    d = daily_stats()
    v = daily_vwc()
    # common VWC y-range so panels are comparable
    vlo, vhi = float(v["vwc"].min()), float(v["vwc"].max())
    vpad = 0.02 * (vhi - vlo)

    fig, axes = plt.subplots(4, 1, figsize=(15, 10), sharex=True, sharey=True,
                             gridspec_kw={"hspace": 0.1})
    for ax, line in zip(axes, LINES):
        s = d.filter(pl.col("line") == line)
        x = mdates.date2num(s["day"].to_list())
        c = LINE_COLOR[line]
        ax.fill_between(x, s["q25"].to_numpy(), s["q75"].to_numpy(),
                        color=c, alpha=0.25, lw=0, label="ρₐ IQR (25–75 %)")
        ax.plot(x, s["med"].to_numpy(), color=c, lw=1.0, marker=".", ms=3,
                label="ρₐ daily median")
        ax.set_ylabel(f"line {line}\nρₐ [Ω·m]")
        ax.set_ylim(*RHO_YLIM)
        ax.grid(alpha=0.3)

        # VWC of this line's nearest 40 cm sensor on a twin axis
        vs = v.filter(pl.col("sensor_id") == LINE_SMS[line]).sort("day")
        axv = ax.twinx()
        axv.plot(mdates.date2num(vs["day"].to_list()), vs["vwc"].to_numpy(),
                 color=VWC_COLOR, lw=1.0, ls="--",
                 label=f"40 cm VWC ({LINE_SMS[line]}, {LINE_POS[line]})")
        axv.set_ylim(vlo - vpad, vhi + vpad)
        axv.set_ylabel("VWC\n[m³/m³]", color=VWC_COLOR)
        axv.tick_params(axis="y", labelcolor=VWC_COLOR)

        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = axv.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper right", ncol=3)

    axes[0].set_title("Daily Wenner apparent resistivity per line (median + IQR, kept "
                      "quads) vs nearest 40 cm soil moisture", fontsize=12)
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].set_xlim(mdates.date2num(d["day"].min()), mdates.date2num(d["day"].max()))
    axes[-1].set_xlabel("date")

    out = OUT_DIR / "wenner_rho_daily.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
