"""Line E investigation.

(1) spatial fault map: per-electrode reciprocal error + contact resistance along
    the line, to localise the fault.
(2) SP(t) drift diagnostic: for a good vs a strong-but-broken quad, recover the
    self-potential at each +/- cycle midpoint  SP = (V+ + V-)/2  and the signal
    IR = (V+ - V-)/2, and fit a line to SP(t). Flat SP -> sign-flip is enough;
    sloped SP -> needs a linear-drift correction (the static/dynamic/linear story).
"""

from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from ohmpi_loader import CACHE_DIR, build_survey_index, load_waveforms
from test_circuit import add_pulse_structure

PLOT_DIR = Path(__file__).resolve().parents[1] / "plots" / "qc_overview"
DROP = {date(2025, 4, 22), date(2025, 4, 23), date(2025, 4, 24)}
ELEC = [49, 50, 51, 52, 53, 54, 56, 57, 58, 59]
GOOD = "56_59_57_58"
BAD = "56_57_54_58"
EXTRACT = [GOOD, BAD, "53_57_54_56", "52_53_51_54"]
CACHE = CACHE_DIR / "wf_lineE.parquet"


def fault_map() -> None:
    s = pl.read_parquet(CACHE_DIR / "summary_table.parquet")
    ew = s.filter((pl.col("line") == "E") & (pl.col("array") == "wenner")
                  & ~pl.col("timestamp").dt.date().is_in(list(DROP)))
    recip, vmn, rab = [], [], []
    for el in ELEC:
        inq = ew.filter((pl.col("a") == el) | (pl.col("b") == el)
                        | (pl.col("m") == el) | (pl.col("n") == el))
        recip.append(inq["recip_err_pct"].median())
        vmn.append(inq["vmn"].abs().median())
        rab.append(inq["rab"].median())

    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(ELEC))
    bars = ax.bar(x, recip, color=["tab:green" if r < 50 else "tab:red" for r in recip])
    ax.axhline(50, color="k", lw=0.7, ls="--")
    ax.set_xticks(x); ax.set_xticklabels(ELEC)
    ax.set_xlabel("electrode # along line E"); ax.set_ylabel("median reciprocal error [%]")
    ax.set_title("Line E fault map (wenner): central electrodes 51–57 are broken")
    ax2 = ax.twinx()
    ax2.plot(x, rab, "o-", color="tab:purple", label="contact resistance rab [kΩ]")
    ax2.set_ylabel("contact resistance rab [kΩ]", color="tab:purple")
    ax2.tick_params(axis="y", labelcolor="tab:purple")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lineE_fault_map.png", dpi=130)
    plt.close(fig)


def get_waveforms() -> pl.DataFrame:
    if CACHE.exists():
        return pl.read_parquet(CACHE)
    idx = build_survey_index().filter((pl.col("array") == "wenner") & (pl.col("line") == "E"))
    wf = load_waveforms(EXTRACT, index=idx)
    wf.write_parquet(CACHE)
    return wf


def cycle_midpoints(wf: pl.DataFrame, quad: str, ts) -> pl.DataFrame:
    """Per +/- on-pulse PAIR: time, SP=(V+ + V-)/2, IR=(V+ - V-)/2."""
    d = wf.filter((pl.col("quad") == quad) & (pl.col("timestamp") == ts))
    pp = (d.group_by("pulse_id", maintain_order=True).agg(
            pol=pl.col("polarity").first(),
            t=pl.col("time").filter("steady").mean(),
            mV=pl.col("voltage").filter("steady").mean(),
        ).filter(pl.col("pol") != 0).sort("pulse_id"))
    # pair each on-pulse with the next one (opposite polarity)
    pp = pp.with_columns(
        mV2=pl.col("mV").shift(-1), pol2=pl.col("pol").shift(-1), t2=pl.col("t").shift(-1)
    ).filter(pl.col("pol2") == -pl.col("pol")).with_columns(
        tmid=(pl.col("t") + pl.col("t2")) / 2,
        SP=(pl.col("mV") + pl.col("mV2")) / 2,
        IR=((pl.col("mV") - pl.col("mV2")) * pl.col("pol")) / 2,
    )
    return pp.select("tmid", "SP", "IR")


def drift_diagnostic(wf: pl.DataFrame) -> None:
    ts = wf.filter(pl.col("quad") == GOOD)["timestamp"].max()
    fig, axes = plt.subplots(2, 2, figsize=(13, 7))
    for col, (quad, label) in enumerate([(GOOD, "good (ends)"), (BAD, "broken (via #54)")]):
        d = wf.filter((pl.col("quad") == quad) & (pl.col("timestamp") == ts)).sort("time")
        cm = cycle_midpoints(wf, quad, ts)
        t, sp = cm["tmid"].to_numpy(), cm["SP"].to_numpy()
        slope, intc = np.polyfit(t, sp, 1)

        axes[0, col].plot(d["time"], d["voltage"], ".-", ms=2, lw=0.4, color="tab:gray")
        axes[0, col].set_title(f"{quad}  —  {label}", loc="left")
        axes[0, col].set_ylabel("raw V [mV]"); axes[0, col].grid(alpha=0.3)

        axes[1, col].scatter(t, sp, s=18, color="tab:red", label="SP = (V₊+V₋)/2")
        axes[1, col].plot(t, slope * t + intc, color="k", lw=1,
                          label=f"fit: {slope:+.1f} mV/s")
        axes[1, col].scatter(t, cm["IR"].to_numpy(), s=14, color="tab:blue",
                             label="signal IR = (V₊−V₋)/2")
        axes[1, col].axhline(0, color="k", lw=0.6)
        axes[1, col].set_xlabel("time within survey [s]")
        axes[1, col].set_ylabel("mV"); axes[1, col].grid(alpha=0.3)
        axes[1, col].legend(loc="best", fontsize=8)
    fig.suptitle(f"Line E SP-drift diagnostic, survey {ts:%Y-%m-%d}")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lineE_sp_drift.png", dpi=130)
    plt.close(fig)


def drift_slopes(wf: pl.DataFrame) -> None:
    """Distribution of the SP drift slope across all surveys: good vs broken quad."""
    fig, ax = plt.subplots(figsize=(8, 4))
    for quad, label, color in [(GOOD, "good (ends)", "tab:green"), (BAD, "broken (#54)", "tab:red")]:
        slopes = []
        for ts in wf.filter(pl.col("quad") == quad)["timestamp"].unique():
            cm = cycle_midpoints(wf, quad, ts)
            if cm.height >= 3:
                t, sp = cm["tmid"].to_numpy(), cm["SP"].to_numpy()
                slopes.append(np.polyfit(t, sp, 1)[0])
        ax.hist(slopes, bins=60, range=(-30, 30), alpha=0.6, color=color,
                label=f"{quad} {label} (med |slope| {np.median(np.abs(slopes)):.1f} mV/s)")
    ax.set_xlabel("SP drift slope per survey [mV/s]"); ax.set_ylabel("surveys")
    ax.set_title("SP drift during the measurement — good vs broken line-E quad")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lineE_sp_slopes.png", dpi=130)
    plt.close(fig)


LABELS = {
    GOOD: "good (ends 56-59)",
    BAD: "broken (via #54)",
    "53_57_54_56": "broken (via #54)",
    "52_53_51_54": "weak+broken (51-54)",
}


def plot_full_waveforms(wf: pl.DataFrame) -> None:
    """Raw full waveforms for several line-E quads, one recent survey, shared time."""
    ts = wf.filter(pl.col("quad") == GOOD)["timestamp"].max()
    fig, axes = plt.subplots(len(EXTRACT), 1, figsize=(12, 11), sharex=True)
    for ax, quad in zip(axes, EXTRACT):
        d = wf.filter((pl.col("quad") == quad) & (pl.col("timestamp") == ts)).sort("time")
        ax.plot(d["time"], d["voltage"], ".-", ms=2, lw=0.4, color="tab:blue")
        ax.set_ylabel("V [mV]")
        ax.set_title(f"{quad}  —  {LABELS[quad]}", loc="left", fontsize=10)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("time within survey [s]")
    fig.suptitle(f"Line E raw full waveforms, survey {ts:%Y-%m-%d} (note the y-scales)", y=0.995)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lineE_full_waveforms.png", dpi=130)
    plt.close(fig)


def plot_waveforms_over_time(wf: pl.DataFrame) -> None:
    """Every sample vs absolute date, good vs broken quad."""
    w = wf.with_columns(
        (pl.col("timestamp") + pl.duration(milliseconds=pl.col("time") * 1000)).alias("abs_t")
    )
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    for ax, quad in zip(axes, [GOOD, BAD]):
        d = w.filter(pl.col("quad") == quad)
        ax.scatter(d["abs_t"], d["voltage"], s=1, alpha=0.2, color="tab:blue", rasterized=True)
        ax.set_ylabel("V [mV]")
        ax.set_title(f"{quad}  —  {LABELS[quad]}", loc="left", fontsize=10)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("date")
    fig.suptitle("Line E full-waveform voltage over the campaign", y=0.995)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "lineE_waveform_over_time.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    fault_map()
    wf = add_pulse_structure(get_waveforms())
    drift_diagnostic(wf)
    drift_slopes(wf)
    plot_full_waveforms(wf)
    plot_waveforms_over_time(wf)
    print(f"plots -> {PLOT_DIR}")
