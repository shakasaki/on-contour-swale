"""Clean per-(survey, quad) resistance table for lines A–D via the sign-flip estimator.

The instrument `_results.csv` reports an `r` that leans on biased off-pulse SP
subtraction; `test_circuit.py` showed the unbiased estimator is the sign-flip
half-cycle average

    R = sum(V_steady · polarity) / sum(I_steady · polarity)

which stacks the +/- half-cycles so the self-potential cancels (validated at
~100 Ω on the reference circuit all year). This script applies that estimator
to *every* A–D quad, survey by survey, streaming one waveform zip at a time so
the full A–D waveform set never sits in memory at once.

QC classification (per quad, over the whole campaign, from the cheap summary
table): a quad is **kept** if median |vmn| ≥ VMN_MIN mV AND median reciprocal
error ≤ RECIP_MAX %. The vmn threshold is insensitive between 1–5 mV — quads
separate cleanly into a strong cluster and a dead cluster — so the recip cut
does the real work. Line E is dropped wholesale (central-electrode hardware
fault, see TODO / line_e_drilldown.py).

Outputs (ohmpi/cache, ohmpi/plots/r_table):
  cache/r_table.parquet     one row per (survey, quad) for A–D: R, n_pulse,
                            R_rec, recip_err_pct, keep flag + QC medians
  cache/quad_qc.parquet     one row per quad: QC medians + keep flag
  plots/r_table/...         kept-vs-dropped representative R series + summary
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl

from geometry import add_geometry
from ohmpi_loader import CACHE_DIR, build_survey_index

PLOT_DIR = Path(__file__).resolve().parents[1] / "plots" / "r_table"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

LINES = ["A", "B", "C", "D"]          # E dropped: central-electrode hardware fault
WINDOW = 0.33                          # steady-state tail fraction of each pulse
VMN_MIN = 1.0                          # mV  — keep if median |vmn| ≥ this
RECIP_MAX = 5.0                        # %   — keep if median reciprocal error ≤ this
DROP_DAYS = {date(2025, 4, 22), date(2025, 4, 23), date(2025, 4, 24)}  # test-circuit ~205 Ω
TEST_CIRCUIT = {"60_61_62_64", "62_64_60_61"}  # ~100 Ω reference resistor, not earth

R_CACHE = CACHE_DIR / "r_table.parquet"
QC_CACHE = CACHE_DIR / "quad_qc.parquet"


# --------------------------------------------------------------------------- QC
def classify_quads() -> pl.DataFrame:
    """One row per (array, line, quad): campaign-median |vmn|, recip error, keep flag.

    Uses the cheap instrument summary table (no waveform extraction). `keep` is
    the per-quad median cut; `n` is the number of surveys the quad appears in.
    """
    s = pl.read_parquet(CACHE_DIR / "summary_table.parquet")
    s = s.with_columns(pl.col("timestamp").dt.date().alias("day"))
    s = s.filter(
        pl.col("line").is_in(LINES) & ~pl.col("day").is_in(list(DROP_DAYS))
    )
    return (
        s.group_by("array", "line", "quad")
        .agg(
            med_vmn=pl.col("vmn").abs().median(),
            med_recip=pl.col("recip_err_pct").median(),
            n=pl.len(),
        )
        .filter(pl.col("n") > 30)
        .with_columns(
            (
                (pl.col("med_vmn") >= VMN_MIN)
                & (pl.col("med_recip") <= RECIP_MAX)
                & pl.col("med_recip").is_not_null()
            ).alias("keep")
        )
        .sort("array", "line", "med_vmn", descending=[False, False, True])
    )


# ---------------------------------------------------------------- sign-flip R
def survey_resistance(fw: pl.DataFrame) -> pl.DataFrame:
    """Sign-flip resistance for every quad in one survey's waveform frame.

    `fw` must carry a `quad` column. Segments each quad's time-ordered trace into
    polarity runs (pulses), takes the steady tail (last WINDOW fraction) of each
    on-pulse, and combines the half-cycles as R = Σ(V·pol)/Σ(I·pol).
    """
    w = fw.sort(["quad", "time"])
    new_pulse = (
        (pl.col("polarity") != pl.col("polarity").shift())
        | (pl.col("quad") != pl.col("quad").shift())
    ).fill_null(True)
    w = w.with_columns(new_pulse.cum_sum().alias("pulse_id"))
    w = w.with_columns(
        (
            pl.col("time").rank("ordinal").over("pulse_id")
            > pl.len().over("pulse_id") * (1 - WINDOW)
        ).alias("steady")
    )
    pulses = (
        w.filter(pl.col("polarity") != 0)
        .group_by(["quad", "pulse_id"], maintain_order=True)
        .agg(
            polarity=pl.col("polarity").first(),
            mV=pl.col("voltage").filter("steady").mean(),
            mI=pl.col("current").filter("steady").mean(),
            a=pl.col("a").first(),
            b=pl.col("b").first(),
            m=pl.col("m").first(),
            n=pl.col("n").first(),
        )
        .with_columns(
            (pl.col("mV") * pl.col("polarity")).alias("sV"),
            (pl.col("mI") * pl.col("polarity")).alias("sI"),
        )
    )
    return pulses.group_by("quad").agg(
        R=pl.col("sV").sum() / pl.col("sI").sum(),
        n_pulse=pl.len(),
        a=pl.col("a").first(),
        b=pl.col("b").first(),
        m=pl.col("m").first(),
        n=pl.col("n").first(),
    )


def build_r_table(index: pl.DataFrame) -> pl.DataFrame:
    """Stream every A–D survey zip once; sign-flip R per (survey, quad).

    Adds the in-survey reciprocal R (quad m_n_a_b measured in the same survey)
    and the resulting waveform-based reciprocal error.
    """
    idx = index.filter(pl.col("line").is_in(LINES))
    frames, bad = [], []
    for i, row in enumerate(idx.iter_rows(named=True), 1):
        try:
            with zipfile.ZipFile(row["fw_zip"]) as zf:
                members = [n for n in zf.namelist() if n.endswith("_fw.csv")]
                if not members:
                    continue
                raw = zf.read(members[0])
        except zipfile.BadZipFile:
            bad.append(row["fw_zip"])
            continue
        fw = pl.read_csv(io.BytesIO(raw)).with_columns(
            pl.concat_str(["a", "b", "m", "n"], separator="_").alias("quad")
        )
        r = survey_resistance(fw).with_columns(
            pl.lit(row["timestamp"]).alias("timestamp"),
            pl.lit(row["array"]).alias("array"),
            pl.lit(row["line"]).alias("line"),
        )
        frames.append(r)
        if i % 200 == 0:
            print(f"  ... {i}/{idx.height} surveys")

    if bad:
        print(f"WARNING: skipped {len(bad)} unreadable zip(s)")
    out = pl.concat(frames, how="diagonal_relaxed")

    # in-survey reciprocal (m_n_a_b) → reciprocal error from the sign-flip R
    out = out.with_columns(
        pl.concat_str(["m", "n", "a", "b"], separator="_").alias("recip_quad")
    )
    rec = out.select(
        ["timestamp", "array", "quad", "R"]
    ).rename({"quad": "recip_quad", "R": "R_rec"})
    out = out.join(rec, on=["timestamp", "array", "recip_quad"], how="left")
    out = out.with_columns(
        (
            (pl.col("R") - pl.col("R_rec")).abs()
            / ((pl.col("R") + pl.col("R_rec")).abs() / 2)
            * 100
        ).alias("recip_err_pct"),
        pl.col("timestamp").dt.date().alias("day"),
    )
    out = out.with_columns(
        pl.col("day").is_in(list(DROP_DAYS)).alias("drop_day")
    )
    return out.sort(["array", "line", "quad", "timestamp"])


# --------------------------------------------------------------------- plots
def plot_kept_vs_dropped(r: pl.DataFrame, qc: pl.DataFrame, array: str) -> None:
    """Representative R(t) for a few kept and a few dropped EARTH quads, per line.

    Excludes the test-circuit reference (100 Ω, 200× the earth signal) and the
    known-bad calibration days so the earth-quad behaviour is on a readable scale.
    """
    rr = r.filter(~pl.col("drop_day") & ~pl.col("quad").is_in(list(TEST_CIRCUIT)))
    fig, axes = plt.subplots(len(LINES), 2, figsize=(14, 11), sharex=True)
    for axrow, line in zip(axes, LINES):
        q = qc.filter(
            (pl.col("array") == array)
            & (pl.col("line") == line)
            & ~pl.col("quad").is_in(list(TEST_CIRCUIT))
        )
        kept = q.filter("keep").sort("med_vmn", descending=True)["quad"].to_list()[:4]
        dropped = q.filter(~pl.col("keep")).sort("med_recip", descending=True)["quad"].to_list()[:4]
        for ax, quads, label in (
            (axrow[0], kept, "kept"),
            (axrow[1], dropped, "dropped"),
        ):
            for quad in quads:
                d = rr.filter(
                    (pl.col("array") == array)
                    & (pl.col("line") == line)
                    & (pl.col("quad") == quad)
                ).sort("timestamp")
                ax.plot(d["timestamp"], d["R"], ".-", ms=2, lw=0.5, alpha=0.8, label=quad)
            ax.axhline(0, color="k", lw=0.6)
            ax.grid(alpha=0.3)
            if quads:
                ax.legend(fontsize=6, ncol=2, loc="upper right")
            if label == "kept":
                ax.set_ylabel(f"line {line}\nR [Ω]")
        axrow[0].set_title(f"kept (median |vmn|≥{VMN_MIN:g} mV, recip≤{RECIP_MAX:g}%)"
                           if line == "A" else "", fontsize=10)
        axrow[1].set_title("dropped" if line == "A" else "", fontsize=10)
    fig.suptitle(f"{array}: sign-flip R(t) — kept vs dropped earth quads, lines A–D "
                 f"(test circuit + bad days excluded)", y=0.995)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / f"kept_vs_dropped_{array}.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_qc_scatter(qc: pl.DataFrame) -> None:
    """Per-quad signal vs reciprocal error with the keep box, A–D, both arrays."""
    arrays = ["dipdip", "wenner"]
    fig, axes = plt.subplots(len(arrays), len(LINES), figsize=(16, 7),
                             sharex=True, sharey=True)
    for axrow, array in zip(axes, arrays):
        for ax, line in zip(axrow, LINES):
            d = qc.filter((pl.col("array") == array) & (pl.col("line") == line))
            for flag, color in [(True, "tab:green"), (False, "tab:red")]:
                dd = d.filter(pl.col("keep") == flag)
                ax.scatter(dd["med_vmn"], dd["med_recip"], s=20, alpha=0.7, color=color)
            ax.axhline(RECIP_MAX, color="0.4", lw=0.8, ls="--")
            ax.axvline(VMN_MIN, color="0.4", lw=0.8, ls="--")
            ax.set_xscale("log"); ax.set_yscale("log")
            ax.grid(alpha=0.3, which="both")
            if array == "dipdip":
                ax.set_title(f"line {line}", fontsize=10)
            if line == "A":
                ax.set_ylabel(f"{array}\nmedian recip err [%]")
            if array == "wenner":
                ax.set_xlabel("median |vmn| [mV]")
    fig.suptitle("Per-quad QC: green = kept, red = dropped (A–D)")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "qc_scatter_AD.png", dpi=130, bbox_inches="tight")
    plt.close(fig)


def report(qc: pl.DataFrame) -> None:
    print("\nkept / total quads per (array, line):")
    summary = (
        qc.group_by("array", "line")
        .agg(kept=pl.col("keep").sum(), total=pl.len())
        .sort("array", "line")
    )
    for row in summary.iter_rows(named=True):
        print(f"  {row['array']:6s} {row['line']}: {row['kept']:2d} / {row['total']:2d}")
    print("\ndropped quads (examples, by line):")
    for (array, line), g in qc.filter(~pl.col("keep")).group_by(
        ["array", "line"], maintain_order=True
    ):
        quads = g.sort("med_recip", descending=True)["quad"].to_list()
        print(f"  {array:6s} {line}: {len(quads):2d} dropped — e.g. {quads[:5]}")


if __name__ == "__main__":
    qc = classify_quads()
    qc.write_parquet(QC_CACHE)
    report(qc)

    if R_CACHE.exists():
        print(f"\nreusing {R_CACHE}")
        r = pl.read_parquet(R_CACHE)
    else:
        idx = build_survey_index()
        print(f"\nstreaming {idx.filter(pl.col('line').is_in(LINES)).height} A–D surveys ...")
        r = build_r_table(idx)
        # attach the per-quad QC flag + medians, then the geometric factor + ρ_a
        r = r.join(
            qc.select(["array", "line", "quad", "keep", "med_vmn", "med_recip"]),
            on=["array", "line", "quad"],
            how="left",
        )
        r = add_geometry(r)
        r.write_parquet(R_CACHE)

    print(f"\nr_table: {r.height} (survey × quad) rows, "
          f"{r.filter('keep').height} on kept quads")
    tc = r.filter(pl.col("quad") == "60_61_62_64")
    if tc.height:
        print(f"test-circuit quad median R = {tc['R'].median():.2f} Ω "
              f"(sanity: expect ~100)")
    ke = r.filter(pl.col("keep") & ~pl.col("drop_day") & pl.col("rho_a").is_not_null())
    print("median apparent resistivity ρ_a on kept earth quads:")
    for row in ke.group_by("array").agg(
        rho=pl.col("rho_a").median(), n=pl.len()
    ).sort("array").iter_rows(named=True):
        print(f"  {row['array']:6s}: {row['rho']:.2f} Ω·m  ({row['n']} rows)")

    plot_qc_scatter(qc)
    for array in ["dipdip", "wenner"]:
        plot_kept_vs_dropped(r, qc, array)
    print(f"\nplots -> {PLOT_DIR}")
