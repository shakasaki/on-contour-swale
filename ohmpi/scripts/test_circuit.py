"""Test-circuit (~100 Ohm reference resistor, quad 60_61_62_64) behaviour over the
whole campaign, with DYNAMIC self-potential (SP) correction.

Method per survey:
  - segment the waveform into pulses (off=0 / on=+-1 runs);
  - steady window = last `WINDOW` fraction of each pulse;
  - dynamic SP for an on-pulse = steady level of the immediately preceding off-pulse;
  - R per on-pulse = (V_on - SP) / I_on  (positive for both polarities: V and I flip
    together, which is the sign-flip that stacks +/- cycles and cancels polarization);
  - average over the survey's pulses -> one R per survey -> one mean R per day.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl

from ohmpi_loader import CACHE_DIR, build_survey_index, load_waveforms

PLOT_DIR = Path(__file__).resolve().parents[1] / "plots" / "qc_waveforms"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

QUAD = "60_61_62_64"          # forward test circuit
RECIP = "62_64_60_61"         # its reciprocal, measured right after
WINDOW = 0.33                 # steady-state fraction at the tail of each pulse
CACHE = CACHE_DIR / "wf_testcircuit.parquet"


def get_waveforms() -> pl.DataFrame:
    if CACHE.exists():
        return pl.read_parquet(CACHE)
    idx = build_survey_index()
    print(f"extracting test circuit from all {idx.height} surveys ...")
    wf = load_waveforms([QUAD, RECIP], index=idx)
    wf.write_parquet(CACHE)
    return wf


def add_pulse_structure(wf: pl.DataFrame) -> pl.DataFrame:
    """Label pulses and flag the steady-state window (last WINDOW fraction of each)."""
    wf = wf.sort(["quad", "timestamp", "time"])
    new_pulse = (
        (pl.col("polarity") != pl.col("polarity").shift())
        | (pl.col("timestamp") != pl.col("timestamp").shift())
        | (pl.col("quad") != pl.col("quad").shift())
    ).fill_null(True)
    wf = wf.with_columns(new_pulse.cum_sum().alias("pulse_id"))
    return wf.with_columns(
        (pl.col("time").rank("ordinal").over("pulse_id") > pl.len().over("pulse_id") * (1 - WINDOW)).alias("steady")
    )


def per_pulse_table(wf: pl.DataFrame) -> pl.DataFrame:
    """One row per on-pulse: polarity, steady-window mean V/I, off-pulse level (SP_off),
    and signed V/I (negative cycle flipped). Carries both estimators:
      R_off  = (V - SP_off)/I       biased per half-cycle (off level is polarization)
      signed_V / signed_I           combined across cycles -> SP cancels (method B)
    """
    pulses = (
        wf.group_by(["quad", "timestamp", "pulse_id"], maintain_order=True).agg(
            polarity=pl.col("polarity").first(),
            mV=pl.col("voltage").filter("steady").mean(),
            mI=pl.col("current").filter("steady").mean(),
        )
        .sort(["quad", "timestamp", "pulse_id"])
        .with_columns(pl.col("mV").shift(1).over(["quad", "timestamp"]).alias("SP_off"))
    )
    return pulses.filter(pl.col("polarity") != 0).with_columns(
        ((pl.col("mV") - pl.col("SP_off")) / pl.col("mI")).alias("R_off"),
        (pl.col("mV") * pl.col("polarity")).alias("signed_V"),
        (pl.col("mI") * pl.col("polarity")).alias("signed_I"),
    )


def daily_resistance(on_pulses: pl.DataFrame) -> pl.DataFrame:
    # method B: signed means cancel SP -> one R per survey
    per_survey = on_pulses.group_by(["quad", "timestamp"]).agg(
        R=(pl.col("signed_V").sum() / pl.col("signed_I").sum()),
        n_pulse=pl.len(),
    )
    return (
        per_survey.with_columns(pl.col("timestamp").dt.date().alias("day"))
        .group_by(["quad", "day"])
        .agg(R=pl.col("R").mean(), R_sd=pl.col("R").std(), n=pl.len())
        .sort(["quad", "day"])
    )


def plot_correction_check(wf: pl.DataFrame) -> None:
    """One survey: raw waveform vs sign-flipped on-pulse samples (method B).

    Sign-flipping (V·polarity) stacks both half-cycles onto a single +IR plateau;
    the implied SP — midpoint of the +/- plateaus — sits near 0, the point being
    that the +50 mV off-time level is polarization, NOT the baseline to subtract.
    """
    ts = wf.filter(pl.col("quad") == QUAD)["timestamp"].max()
    d = wf.filter((pl.col("quad") == QUAD) & (pl.col("timestamp") == ts)).sort("time")
    on = d.filter(pl.col("polarity") != 0).with_columns(
        (pl.col("voltage") * pl.col("polarity")).alias("V_flip")
    )
    off_level = d.filter(pl.col("polarity") == 0)["voltage"].median()

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].plot(d["time"], d["voltage"], ".-", ms=2, lw=0.5, color="tab:gray")
    axes[0].axhline(off_level, color="tab:red", lw=1, ls="--",
                    label=f"off-time level = {off_level:.0f} mV (polarization, not SP)")
    axes[0].axhline(0, color="k", lw=0.8)
    axes[0].set_ylabel("raw V [mV]")
    axes[0].set_title(f"Test circuit {QUAD}, survey {ts:%Y-%m-%d %H:%M}", loc="left")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].scatter(on["time"], on["V_flip"], s=6, color="tab:blue",
                    label="on-pulse · polarity (both half-cycles stacked)")
    axes[1].axhline(on["V_flip"].median(), color="tab:green", lw=1, ls="--",
                    label=f"IR plateau = {on['V_flip'].median():.0f} mV")
    axes[1].set_ylabel("V · polarity [mV]")
    axes[1].set_xlabel("time within survey [s]")
    axes[1].set_title("sign-flip method: half-cycles stack at +IR, SP cancels (baseline ≈ 0)", loc="left")
    axes[1].grid(alpha=0.3)
    axes[1].legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "testcircuit_correction_check.png", dpi=130)
    plt.close(fig)


def plot_method_compare(on_pulses: pl.DataFrame) -> None:
    """Per-half-cycle R from off-subtraction (two biased clouds) vs per-survey R from
    the sign-flip average (one clean cloud at ~100 Ohm)."""
    a = on_pulses.filter(pl.col("quad") == QUAD)
    pos = a.filter(pl.col("polarity") == 1)["R_off"]
    neg = a.filter(pl.col("polarity") == -1)["R_off"]
    b = (a.group_by("timestamp").agg(
            R=(pl.col("signed_V").sum() / pl.col("signed_I").sum()))["R"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), sharey=False)
    axes[0].hist(pos, bins=80, range=(0, 200), alpha=0.7, label=f"+ cycle (med {pos.median():.0f} Ω)")
    axes[0].hist(neg, bins=80, range=(0, 200), alpha=0.7, label=f"− cycle (med {neg.median():.0f} Ω)")
    axes[0].axvline(100, color="k", lw=0.8, ls="--")
    axes[0].set_title("A) off-pulse subtraction — biased per half-cycle")
    axes[0].set_xlabel("R per half-cycle [Ω]"); axes[0].legend()

    axes[1].hist(b, bins=80, range=(80, 130), color="tab:green",
                 label=f"per survey (med {b.median():.1f} Ω)")
    axes[1].axvline(100, color="k", lw=0.8, ls="--")
    axes[1].set_title("B) sign-flip half-cycle average — unbiased")
    axes[1].set_xlabel("R per survey [Ω]"); axes[1].legend()
    fig.suptitle(f"Why the off-pulse is not the SP — test circuit {QUAD}")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "testcircuit_method_compare.png", dpi=130)
    plt.close(fig)


def plot_daily(daily: pl.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(13, 5))
    for quad, color in [(QUAD, "tab:blue"), (RECIP, "tab:orange")]:
        d = daily.filter(pl.col("quad") == quad)
        ax.errorbar(d["day"], d["R"], yerr=d["R_sd"], fmt="o", ms=3, lw=0.6,
                    capsize=2, color=color, alpha=0.8,
                    label=f"{quad}  (median {d['R'].median():.1f} Ω)")
    ax.set_ylabel("daily mean R [Ω]")
    ax.set_xlabel("date")
    ax.set_title("Test-circuit resistance per day — dynamic SP correction, both half-cycles")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "testcircuit_daily_R.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    wf = add_pulse_structure(get_waveforms())
    on_pulses = per_pulse_table(wf)
    daily = daily_resistance(on_pulses)

    fwd = daily.filter(pl.col("quad") == QUAD)
    print(f"test circuit {QUAD}: {fwd.height} days, "
          f"median daily R = {fwd['R'].median():.2f} Ω, "
          f"day-to-day sd = {fwd['R'].std():.2f} Ω")
    print(f"range: {fwd['R'].min():.2f} – {fwd['R'].max():.2f} Ω")

    plot_correction_check(wf)
    plot_method_compare(on_pulses)
    plot_daily(daily)
    print(f"plots -> {PLOT_DIR}")
