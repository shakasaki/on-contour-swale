"""Frequency-domain decomposition of soil-moisture time series.

Computes a power spectral density (Welch periodogram) per moisture sensor,
faceted by depth and colored by treatment. Goal: expose the dominant
periodicities (daily ET cycle, semi-diurnal, weekly rain spacing, seasonal
trend residual) so we can see which timescales carry the most variance.

Run from project root::

    .venv/bin/python scripts/spectrum.py

Method notes
------------
- Resample each sensor onto a fixed 15-min grid (native cadence).
- Linear-interpolate gaps up to 4 h; take the longest contiguous run with
  no remaining nulls (FFT requires a uniformly-sampled, gap-free segment).
- Linear-detrend before transforming so a multi-month dry/wet trend doesn't
  swamp the daily/weekly bands.
- scipy.signal.welch with a 7-day window (nperseg=672) for variance
  reduction; sets the lowest resolved period at ~1 week.

Caveat: a global PSD averages over the whole record, so it shows
*persistent* periodicities. The post-rain drydown slope is a transient
event — to characterize it directly, the next pass should use STFT
(scipy.signal.spectrogram) for time-localized spectra, or detect rain
events and fit exponential decays to the moisture recession.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates  # noqa: F401  (keeps the import grouped)
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from scipy import signal

from swale.config import load_settings
from swale.loader import load_swale_dataset
from swale.preprocessing import (
    GRID_SECONDS,
    SAMPLES_PER_DAY,
    regular_series,
)

# Project layout
ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

# Treatment styling. Color alone wasn't enough to read at-a-glance, so each
# treatment also gets a distinct line style.
COLOR = {"swale": "#1f77b4", "control": "#d62728"}
LINESTYLE = {"swale": "-", "control": "--"}

# Welch parameters
NPERSEG = SAMPLES_PER_DAY * 7         # 672 = one-week window
NOVERLAP = NPERSEG // 2

# Surfaced for the empty-panel message (matches preprocessing default)
MIN_SEGMENT_DAYS = 30

# Depth facets. SMS23/SMS24 still have no recorded depth (TODO: Location=?)
# but they also have no treatment, so the treatment filter excludes them
# upstream. If they ever get assigned, add a (None, ...) row here.
DEPTH_FACETS: list[tuple[int, str]] = [
    (-10, "Above ground (-10 cm, on mound)"),
    (10,  "Topsoil (10 cm)"),
    (40,  "Subsoil (40 cm)"),
]


# ---------------------------------------------------------------------------
# PSD computation
# ---------------------------------------------------------------------------

def compute_psd(values: np.ndarray,
                *, nperseg_samples: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (period_hours, psd) via Welch on a linearly-detrended series.

    ``nperseg_samples`` is the segment length in 15-min samples. Smaller =
    more averaging (cleaner spectrum) but cuts off at longer periods.
    Larger = reaches lower frequencies but noisier per bin. When the value
    equals (or exceeds) the series length, Welch reduces to a single
    periodogram — fine-resolution but no variance reduction.
    """
    detrended = signal.detrend(values, type="linear")
    fs = 1.0 / GRID_SECONDS
    nperseg = min(nperseg_samples, len(detrended))
    freqs, psd = signal.welch(
        detrended,
        fs=fs,
        nperseg=nperseg,
        noverlap=nperseg // 2,
        window="hann",
        detrend=False,
    )
    mask = freqs > 0  # drop the DC bin so we can plot log-log
    period_hours = 1.0 / freqs[mask] / 3600.0
    return period_hours, psd[mask]


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

REF_PERIODS_SHORT = [
    (12,        "12 h"),
    (24,        "24 h (daily ET)"),
    (24 * 7,    "1 wk"),
]
REF_PERIODS_LONG = [
    (24,        "1 d"),
    (24 * 7,    "1 wk"),
    (24 * 30,   "1 mo"),
    (24 * 90,   "3 mo"),
    (24 * 365,  "1 yr"),
]


def plot_spectrum(df: pl.DataFrame, out: Path, *,
                    nperseg_samples: int, window_label: str,
                    ref_periods: list[tuple[float, str]]) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    moisture = (df.filter(pl.col("variable") == "moisture")
                  .filter(pl.col("treatment").is_not_null()))

    fig, axes = plt.subplots(len(DEPTH_FACETS), 1, figsize=(10, 9),
                              sharex=True)
    fig.suptitle(f"Soil moisture — PSD by depth × treatment "
                 f"(Welch, {window_label}, linear-detrended)",
                 fontsize=13, weight="bold")

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
            periods, psd = compute_psd(vals, nperseg_samples=nperseg_samples)

            label = treatment if treatment not in seen_treatments else None
            seen_treatments.add(treatment)
            ax.loglog(periods, psd,
                       color=COLOR.get(treatment, "#888"),
                       linestyle=LINESTYLE.get(treatment, "-"),
                       linewidth=1.1, alpha=0.85,
                       label=label)
            n_curves += 1

        for p, txt in ref_periods:
            ax.axvline(p, color="k", linestyle=":", linewidth=0.7, alpha=0.5)
            ax.text(p, 1, txt, rotation=90, va="top", ha="right",
                     fontsize=8, alpha=0.6,
                     transform=ax.get_xaxis_transform())

        ax.set_ylabel(depth_label, fontsize=10)
        ax.set_xlabel("")
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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

    short_out = PLOTS / "02_spectrum.png"
    print(f"Computing 7-day-window PSDs → {short_out}")
    plot_spectrum(df, short_out,
                  nperseg_samples=NPERSEG,
                  window_label="7-day window",
                  ref_periods=REF_PERIODS_SHORT)

    # Long-window pass: use the full segment per sensor (no Welch averaging,
    # finest frequency resolution). Setting nperseg = 365 d on a ~356 d
    # segment makes scipy clamp it down to len(detrended), giving a single
    # periodogram that reaches the lowest frequency the data can support.
    long_out = PLOTS / "02_spectrum_long.png"
    long_nperseg = 365 * SAMPLES_PER_DAY
    print(f"Computing full-record PSDs → {long_out}")
    plot_spectrum(df, long_out,
                  nperseg_samples=long_nperseg,
                  window_label="full-record (≈1 yr) periodogram",
                  ref_periods=REF_PERIODS_LONG)
    print("Done.")


if __name__ == "__main__":
    main()
