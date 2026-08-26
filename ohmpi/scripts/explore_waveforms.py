"""Extract + cache full waveforms for a handful of representative quadrupoles,
then make the two views Alexis asked for: full waveform over the whole campaign,
and value histograms. Good vs bad vs reference, all within dipdip line A.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl

from ohmpi_loader import CACHE_DIR, build_survey_index, load_waveforms

PLOT_DIR = Path(__file__).resolve().parents[1] / "plots" / "qc_waveforms"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# dipdip line A: reference resistor, two strong-signal, two noise-floor quads
QUADS = {
    "60_61_62_64": "test resistor (~100 Ohm)",
    "3_4_5_6": "good: adjacent dipoles",
    "4_5_6_7": "good: adjacent dipoles",
    "1_2_7_9": "noise: wide separation",
    "1_2_10_11": "noise: widest separation",
}
ORDER = list(QUADS)
CACHE = CACHE_DIR / "wf_dipdipA_demo.parquet"


def get_waveforms() -> pl.DataFrame:
    if CACHE.exists():
        return pl.read_parquet(CACHE)
    idx = build_survey_index().filter(
        (pl.col("array") == "dipdip") & (pl.col("line") == "A")
    )
    print(f"extracting {len(QUADS)} quads from {idx.height} surveys ...")
    wf = load_waveforms(ORDER, index=idx)
    wf.write_parquet(CACHE)
    return wf


def plot_waveform_over_time(wf: pl.DataFrame) -> None:
    """Voltage of every sample vs absolute datetime (survey time + intra-survey offset)."""
    wf = wf.with_columns(
        (pl.col("timestamp") + pl.duration(milliseconds=pl.col("time") * 1000)).alias("abs_t")
    )
    fig, axes = plt.subplots(len(ORDER), 1, figsize=(13, 11), sharex=True)
    for ax, quad in zip(axes, ORDER):
        d = wf.filter(pl.col("quad") == quad)
        ax.scatter(d["abs_t"], d["voltage"], s=1, alpha=0.25, color="tab:blue", rasterized=True)
        ax.set_ylabel("V [mV]")
        ax.set_title(f"{quad}  —  {QUADS[quad]}", loc="left", fontsize=10)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("date")
    fig.suptitle("Full-waveform voltage over the campaign — dipdip line A", y=0.995)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "waveform_over_time.png", dpi=130)
    plt.close(fig)


def plot_histograms(wf: pl.DataFrame) -> None:
    """Distribution of on-pulse voltage samples (polarity != 0) per quad."""
    fig, axes = plt.subplots(1, len(ORDER), figsize=(17, 3.4))
    for ax, quad in zip(axes, ORDER):
        v = wf.filter((pl.col("quad") == quad) & (pl.col("polarity") != 0))["voltage"]
        ax.hist(v, bins=120, color="tab:blue")
        ax.set_title(f"{quad}\n{QUADS[quad]}", fontsize=9)
        ax.set_xlabel("V [mV]")
        ax.axvline(0, color="k", lw=0.6)
    axes[0].set_ylabel("count")
    fig.suptitle("On-pulse voltage distribution over the campaign — dipdip line A")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "voltage_histograms.png", dpi=130)
    plt.close(fig)


def plot_example_waveforms(wf: pl.DataFrame) -> None:
    """One recent survey per quad: the raw square wave (V & I), to see SNR by eye."""
    last_ts = wf["timestamp"].max()
    fig, axes = plt.subplots(len(ORDER), 1, figsize=(11, 11), sharex=True)
    for ax, quad in zip(axes, ORDER):
        d = wf.filter((pl.col("quad") == quad) & (pl.col("timestamp") == last_ts)).sort("time")
        ax.plot(d["time"], d["voltage"], ".-", ms=2, lw=0.5, color="tab:blue")
        ax.set_ylabel("V [mV]")
        ax.set_title(f"{quad}  —  {QUADS[quad]}", loc="left", fontsize=10)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("time within survey [s]")
    fig.suptitle(f"Raw waveform, single survey {last_ts:%Y-%m-%d} — dipdip line A", y=0.995)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "example_waveforms.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    wf = get_waveforms()
    print(f"waveform rows: {wf.height}")
    print(wf.group_by("quad").len().sort("quad"))
    plot_waveform_over_time(wf)
    plot_histograms(wf)
    plot_example_waveforms(wf)
    print(f"plots -> {PLOT_DIR}")
