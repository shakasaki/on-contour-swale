"""Campaign-wide QC triage from the cheap instrument summary table (no waveform
extraction). Two views that let you judge every quad at once instead of drowning
in ~90k per-survey plots:

  1. heatmap  quad x time, one panel per line, colour = reciprocal error %.
     persistent hot row = bad quad; row that turns hot = quad degrading;
     blank column = missing/failed day.
  2. scatter  per quad: median signal |vmn| vs median reciprocal error.

Reciprocal error and |vmn| come straight from the instrument `_results.csv`
(already in summary_table.parquet); good enough to triage. The careful
sign-flip resistance estimator is reserved for the quads that survive.
"""

from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from ohmpi_loader import CACHE_DIR

PLOT_DIR = Path(__file__).resolve().parents[1] / "plots" / "qc_overview"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

DROP_DAYS = {date(2025, 4, 22), date(2025, 4, 23), date(2025, 4, 24)}  # test-circuit ~205 Ω
RECIP_CLIP = 30.0   # % — colour saturates here so the green/red split is readable
LINES = ["A", "B", "C", "D", "E"]


def load(array: str) -> pl.DataFrame:
    s = pl.read_parquet(CACHE_DIR / "summary_table.parquet")
    s = s.filter(pl.col("array") == array).with_columns(
        pl.col("timestamp").dt.date().alias("day"),
        pl.col("vmn").abs().alias("absvmn"),
    )
    return s.filter(~pl.col("day").is_in(list(DROP_DAYS)))


def heatmap(array: str) -> None:
    s = load(array)
    days = s["day"].unique().sort()
    day0 = days.min()
    ncol = (days.max() - day0).days + 1
    xidx = {d: (d - day0).days for d in days}

    fig, axes = plt.subplots(len(LINES), 1, figsize=(14, 12), sharex=True)
    im = None
    for ax, line in zip(axes, LINES):
        sub = s.filter(pl.col("line") == line)
        order = (sub.group_by("quad").agg(v=pl.col("absvmn").median())
                    .sort("v", descending=True)["quad"].to_list())
        ridx = {q: i for i, q in enumerate(order)}
        M = np.full((len(order), ncol), np.nan)
        for q, d, e in sub.select("quad", "day", "recip_err_pct").iter_rows():
            if e is not None:
                M[ridx[q], xidx[d]] = min(e, RECIP_CLIP)
        cmap = plt.cm.RdYlGn_r.copy()
        cmap.set_bad("0.85")
        im = ax.imshow(M, aspect="auto", cmap=cmap, vmin=0, vmax=RECIP_CLIP,
                       interpolation="nearest")
        ax.set_ylabel(f"line {line}\n({len(order)} quads)")
        ax.set_yticks([])

    # monthly x ticks
    ticks, labels = [], []
    for d in days:
        if d.day == 1:
            ticks.append(xidx[d]); labels.append(d.strftime("%Y-%m"))
    axes[-1].set_xticks(ticks); axes[-1].set_xticklabels(labels, rotation=45, ha="right")
    axes[-1].set_xlabel("date")
    fig.suptitle(f"{array}: reciprocal error % per quad over the campaign "
                 f"(rows sorted by signal strength; grey = no data)", y=0.995)
    cb = fig.colorbar(im, ax=axes, fraction=0.015, pad=0.01)
    cb.set_label(f"reciprocal error % (clipped at {RECIP_CLIP:g})")
    fig.savefig(PLOT_DIR / f"heatmap_recip_{array}.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def scatter(array: str) -> None:
    s = load(array)
    per_quad = (s.group_by("line", "quad").agg(
        vmn=pl.col("absvmn").median(),
        recip=pl.col("recip_err_pct").median(),
        n=pl.len(),
    ).filter(pl.col("n") > 30))

    fig, axes = plt.subplots(1, len(LINES), figsize=(18, 3.8), sharex=True, sharey=True)
    for ax, line in zip(axes, LINES):
        d = per_quad.filter(pl.col("line") == line)
        ax.scatter(d["vmn"], d["recip"], s=18, alpha=0.7, color="tab:blue")
        ax.axhline(5, color="tab:red", lw=0.8, ls="--")     # candidate recip threshold
        ax.axvline(1, color="tab:red", lw=0.8, ls="--")     # candidate signal threshold
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(f"line {line}", fontsize=10)
        ax.set_xlabel("median |vmn| [mV]")
        ax.grid(alpha=0.3, which="both")
    axes[0].set_ylabel("median reciprocal err [%]")
    fig.suptitle(f"{array}: per-quad signal vs reciprocal error "
                 f"(good = lower-right of the red lines)")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / f"scatter_{array}.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    for array in ["dipdip", "wenner"]:
        heatmap(array)
        scatter(array)
    print(f"plots -> {PLOT_DIR}")
