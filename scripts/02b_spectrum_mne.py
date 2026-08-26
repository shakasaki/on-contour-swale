"""Welch PSD via MNE-Python.

Mirrors scripts/spectrum.py but routes the PSD through MNE's
``mne.time_frequency.psd_array_welch`` instead of scipy. Same depth ×
treatment layout, same per-sensor preprocessing.

Why MNE instead of scipy here: keeps PSD and the upcoming Morlet TFR
(scripts/spectrogram.py) on the same library so frequency conventions and
plotting code stay consistent. The numerical result is the same Welch.

Run from project root::

    .venv/bin/python scripts/spectrum_mne.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from mne.time_frequency import psd_array_welch

from swale.config import load_settings
from swale.loader import load_swale_dataset
from swale.preprocessing import (
    GRID_SECONDS,
    SAMPLES_PER_DAY,
    regular_series,
)

# ---------------------------------------------------------------------------
# Tunables — change these to play with the analysis.
# ---------------------------------------------------------------------------

# Welch segment length (in 15-min samples). 7 days = 672 samples.
N_PER_SEG = SAMPLES_PER_DAY * 7
# Overlap between consecutive segments (50% is standard).
N_OVERLAP = N_PER_SEG // 2
# Frequency band of interest. Periods 30 min ↔ 7 days at 15-min sampling.
FMIN_HZ = 1.0 / (7 * 24 * 3600)
FMAX_HZ = 1.0 / (30 * 60)

# Aggregation across Welch segments: "mean" or "median". Median is more
# robust to single outlier segments (e.g. one weird week).
WELCH_AVERAGE = "mean"

MIN_SEGMENT_DAYS = 30  # used only for the empty-panel message

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

COLOR = {"swale": "#1f77b4", "control": "#d62728"}
LINESTYLE = {"swale": "-", "control": "--"}

DEPTH_FACETS: list[tuple[int, str]] = [
    (-10, "Above ground (-10 cm, on mound)"),
    (10,  "Topsoil (10 cm)"),
    (40,  "Subsoil (40 cm)"),
]

REF_PERIODS = [
    (12,        "12 h"),
    (24,        "24 h (daily ET)"),
    (24 * 7,    "1 wk"),
]


# ---------------------------------------------------------------------------
# PSD via MNE
# ---------------------------------------------------------------------------

def compute_psd_mne(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Welch PSD via mne.time_frequency.psd_array_welch.

    Returns (period_hours, psd) for the linearly-detrended series. MNE
    expects shape (..., n_times) and returns (..., n_freqs); we use a
    single-channel layout.
    """
    # Linear detrend (numpy, since MNE's psd_array_welch doesn't detrend).
    t = np.arange(len(values), dtype=float)
    a, b = np.polyfit(t, values, 1)
    detrended = values - (a * t + b)

    sfreq = 1.0 / GRID_SECONDS
    n_per_seg = min(N_PER_SEG, len(detrended))
    psd, freqs = psd_array_welch(
        detrended[np.newaxis, :],         # (1, n_times)
        sfreq=sfreq,
        fmin=FMIN_HZ,
        fmax=min(FMAX_HZ, sfreq / 2),
        n_fft=n_per_seg,
        n_per_seg=n_per_seg,
        n_overlap=min(N_OVERLAP, n_per_seg // 2),
        window="hann",
        average=WELCH_AVERAGE,
        verbose=False,
    )
    psd = psd[0]                          # drop the singleton channel axis
    mask = freqs > 0
    period_hours = 1.0 / freqs[mask] / 3600.0
    return period_hours, psd[mask]


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_spectrum(df: pl.DataFrame, out: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    moisture = (df.filter(pl.col("variable") == "moisture")
                  .filter(pl.col("treatment").is_not_null()))

    fig, axes = plt.subplots(len(DEPTH_FACETS), 1, figsize=(10, 9),
                              sharex=True)
    fig.suptitle("Soil moisture — Welch PSD via MNE "
                 f"(n_per_seg={N_PER_SEG} samples = {N_PER_SEG/SAMPLES_PER_DAY:.0f} d, "
                 f"average={WELCH_AVERAGE})",
                 fontsize=12, weight="bold")

    for row_i, (depth, depth_label) in enumerate(DEPTH_FACETS):
        ax = axes[row_i]
        bucket = moisture.filter(pl.col("depth_cm") == depth)

        seen_treatments: set[str] = set()
        n_curves = 0
        for sid, group in bucket.group_by("sensor_id", maintain_order=True):
            sid = sid[0] if isinstance(sid, tuple) else sid
            treatment = group["treatment"].drop_nulls().first()
            if treatment is None:
                continue
            seg = regular_series(group)
            if seg is None:
                continue
            _ts, vals = seg
            periods, psd = compute_psd_mne(vals)

            label = treatment if treatment not in seen_treatments else None
            seen_treatments.add(treatment)
            ax.loglog(periods, psd,
                       color=COLOR.get(treatment, "#888"),
                       linestyle=LINESTYLE.get(treatment, "-"),
                       linewidth=1.1, alpha=0.85,
                       label=label)
            n_curves += 1

        for p, txt in REF_PERIODS:
            ax.axvline(p, color="k", linestyle=":", linewidth=0.7, alpha=0.5)
            ax.text(p, 1, txt, rotation=90, va="top", ha="right",
                     fontsize=8, alpha=0.6,
                     transform=ax.get_xaxis_transform())

        ax.set_ylabel(depth_label, fontsize=10)
        if n_curves == 0:
            ax.text(0.5, 0.5, "no usable segment ≥ "
                    f"{MIN_SEGMENT_DAYS} d", ha="center", va="center",
                    transform=ax.transAxes, alpha=0.6)
        if seen_treatments:
            ax.legend(fontsize=9, loc="upper right")

    axes[-1].set_xlabel("Period (hours, log scale)")
    fig.text(0.005, 0.5, r"PSD ((m$^3$/m$^3$)$^2$ · Hz$^{-1}$, log scale)",
              va="center", rotation="vertical", fontsize=10)

    fig.tight_layout(rect=(0.02, 0, 1, 0.97))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print("Loading dataset (cached if available)…")
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )
    print(f"  {df.height:,} rows")

    out = PLOTS / "02b_spectrum_mne.png"
    print(f"Computing MNE Welch PSDs → {out}")
    plot_spectrum(df, out)
    print("Done.")


if __name__ == "__main__":
    main()
