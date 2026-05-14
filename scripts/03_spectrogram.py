"""Per-sensor time-frequency representation of soil moisture.

One figure per depth. Each figure stacks: a precipitation row at the top,
then one spectrogram row per sensor at that depth (4 swale + 3 control at
10 cm; up to 5 swale + 3 control at 40 cm including the 'step' sensor).
All rows share the x-axis and span the full figure width. The two
spectrogram color scales are shared per-figure so swale-vs-control
intensity is directly comparable.

Wavelet choice. Set ``WAVELET`` at the top of the script:

    "morlet"  -> MNE Morlet (complex), balanced time-frequency, default.
    "mexh"    -> pyWavelets Mexican Hat (Ricker). Real-valued. Sharper in
                 time, fuzzier in frequency. Good at edges and peaks —
                 the CWT analog of Haar for sharp transitions.
    "cmor"    -> pyWavelets complex Morlet. Like 'morlet' but routed
                 through pywt for cross-checking.

Note: Haar specifically is a discrete wavelet (DWT only) and pyWavelets
refuses to use it in CWT mode. If you want a strict Haar decomposition,
that's a separate dyadic-scale visualization, not a spectrogram.

Run from project root::

    .venv/bin/python scripts/spectrogram.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import polars as pl
import pywt
import seaborn as sns
from matplotlib.colors import LogNorm
from matplotlib.gridspec import GridSpec
from mne.time_frequency import tfr_array_morlet

from swale.config import load_settings
from swale.loader import load_swale_dataset
from swale.preprocessing import GRID_SECONDS, regular_series

# ---------------------------------------------------------------------------
# Tunables — change these to play with the analysis.
# ---------------------------------------------------------------------------

# Which wavelet drives the TFR. See module docstring.
WAVELET: str = "morlet"          # "morlet" | "mexh" | "cmor"

# Which depths get their own figure. -10 (above-ground "mount" SMS03) is
# explicitly excluded per current request.
DEPTHS_TO_PLOT: list[int] = [10, 40]

# Log-spaced periods to analyse (hours). 3 h ↔ 7 d covers diurnal,
# multi-day drydown, and the short edge of the weekly band.
PERIOD_LOW_HOURS = 3
PERIOD_HIGH_HOURS = 24 * 7
N_FREQS = 30

# n_cycles per frequency in the Morlet wavelet. Constant value: each band
# uses a wavelet of length n_cycles / f, so low frequencies automatically
# get a (proportionally) longer window. Higher n_cycles = sharper in
# frequency, blurrier in time.
# Edge note: at the lowest freq (1/7 d) with n_cycles=7, the wavelet spans
# ~49 days, so the leftmost/rightmost ~50 days of that band are unreliable.
# (Used for "morlet" and "cmor"; "mexh" is parameter-free.)
N_CYCLES = 7.0

# pyWavelets complex Morlet bandwidth & center freq. cmor1.5-1.0 is the
# usual default — narrower bandwidth → sharper in frequency, broader in time.
CMOR_PARAMS = "cmor1.5-1.0"

# Post-TFR time-axis decimation. decim=4 brings 15-min samples down to
# hourly — plenty for visualisation, big speed/memory win.
DECIM = 4

# Maximum gap (seconds) bridged by linear interpolation when picking each
# sensor's longest contiguous run. 24 h bridges the single 15 h dropout
# on 2025-02-12 that otherwise splits the deployment in half.
MAX_INTERP_GAP_S = 24 * 3600

# Treatments to render, in row order.
TREATMENT_ORDER: list[str] = ["swale", "control"]

# Border color around each treatment's row labels (matches PSD palette).
TREATMENT_COLOR = {"swale": "#1f77b4", "control": "#d62728"}

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
TFR_CACHE = CACHE / "tfr"
PLOTS = ROOT / "plots"


# ---------------------------------------------------------------------------
# Sensor enumeration
# ---------------------------------------------------------------------------

def list_sensors_at_depth(df: pl.DataFrame, depth: int):
    """Return [(treatment, sensor_id, location, tag), ...] sorted for plotting.

    Order: all swale sensors first (sorted by sensor_id), then all controls.
    Sensors with no usable contiguous segment are filtered out by the
    caller, not here.
    """
    bucket = (df.filter((pl.col("variable") == "moisture")
                         & (pl.col("depth_cm") == depth)
                         & pl.col("treatment").is_not_null())
                 .select(["sensor_id", "treatment", "location", "tag"])
                 .unique()
                 .sort(["treatment", "sensor_id"]))
    rows = bucket.to_dicts()
    out = []
    for treatment in TREATMENT_ORDER:
        for r in rows:
            if r["treatment"] == treatment:
                out.append((r["treatment"], r["sensor_id"],
                            r["location"], r["tag"]))
    return out


def per_sensor_series(df: pl.DataFrame, sensor_id: str):
    """Return (ts, vals) for the longest gap-bridged contiguous run, or None."""
    g = df.filter((pl.col("variable") == "moisture")
                   & (pl.col("sensor_id") == sensor_id))
    return regular_series(g, max_interp_gap_s=MAX_INTERP_GAP_S)


# ---------------------------------------------------------------------------
# TFR — pluggable per WAVELET
# ---------------------------------------------------------------------------

def _compute_tfr_uncached(values: np.ndarray,
                            freqs_hz: np.ndarray) -> np.ndarray:
    """Run the chosen wavelet backend. Linearly detrends first so the
    multi-month drift doesn't dominate the lowest band.
    """
    t = np.arange(len(values), dtype=float)
    a, b = np.polyfit(t, values, 1)
    detrended = values - (a * t + b)
    sfreq = 1.0 / GRID_SECONDS

    if WAVELET == "morlet":
        epoch = detrended[np.newaxis, np.newaxis, :]   # (1, 1, n_times)
        power = tfr_array_morlet(
            epoch, sfreq=sfreq, freqs=freqs_hz,
            n_cycles=N_CYCLES, output="power",
            decim=DECIM, verbose=False,
        )
        return power[0, 0]

    if WAVELET in {"mexh", "cmor"}:
        # pywt CWT works in scales, not frequencies. Convert via the
        # wavelet's central frequency: scale = fc * sfreq / freq.
        wavelet_name = CMOR_PARAMS if WAVELET == "cmor" else "mexh"
        fc = pywt.central_frequency(wavelet_name)
        scales = fc * sfreq / freqs_hz
        coefs, _ = pywt.cwt(detrended, scales, wavelet_name,
                             sampling_period=1.0 / sfreq)
        # |coef|² = power; mexh is real (so coefs is real), cmor is complex.
        power = np.abs(coefs) ** 2
        # Decimate the time axis to match the morlet path's behavior.
        return power[:, ::DECIM]

    raise ValueError(f"Unknown WAVELET={WAVELET!r}")


def _tfr_cache_path(sensor_id: str, freqs_hz: np.ndarray,
                      values: np.ndarray) -> Path:
    """Build a cache filename keyed on every input that affects the result.

    Hashing the values bytes gives automatic invalidation: if metadata
    changes shift which contiguous segment is selected (different start/
    length, different gap-bridging), the bytes change → hash changes →
    cache miss → recompute.
    """
    h = hashlib.md5()
    h.update(WAVELET.encode())
    h.update(freqs_hz.astype(np.float64).tobytes())
    h.update(np.array([N_CYCLES, DECIM], dtype=np.float64).tobytes())
    if WAVELET == "cmor":
        h.update(CMOR_PARAMS.encode())
    h.update(values.astype(np.float64).tobytes())
    return TFR_CACHE / f"{sensor_id}_{WAVELET}_{h.hexdigest()[:12]}.npz"


def compute_tfr(sensor_id: str, values: np.ndarray,
                 freqs_hz: np.ndarray) -> tuple[np.ndarray, bool]:
    """Cached TFR. Returns (power, was_cached)."""
    path = _tfr_cache_path(sensor_id, freqs_hz, values)
    if path.exists():
        return np.load(path)["power"], True
    power = _compute_tfr_uncached(values, freqs_hz)
    TFR_CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(path, power=power)
    return power, False


# ---------------------------------------------------------------------------
# Precipitation series at native cadence
# ---------------------------------------------------------------------------

def native_rain(df: pl.DataFrame, t0: np.datetime64,
                  t1: np.datetime64) -> tuple[np.ndarray, np.ndarray]:
    """Return (timestamps, mm) at native 5-min cadence in [t0, t1].

    No daily binning — every individual tipping-bucket increment shows up
    as its own spike, so small events stay visible.
    """
    rain = (df.filter((pl.col("logger_serial") == "19570")
                       & (pl.col("variable") == "precipitation")
                       & pl.col("value").is_not_null()
                       & (pl.col("value") > 0)
                       & (pl.col("timestamp") >= t0)
                       & (pl.col("timestamp") <= t1))
              .sort("timestamp"))
    if rain.is_empty():
        return np.array([], dtype="datetime64[ns]"), np.array([])
    return rain["timestamp"].to_numpy(), rain["value"].to_numpy()


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_for_depth(df: pl.DataFrame, depth: int, out: Path) -> None:
    sns.set_theme(style="white", context="paper")

    sensors = list_sensors_at_depth(df, depth)
    if not sensors:
        print(f"  no sensors at {depth} cm; skipping")
        return

    freqs_hz = np.logspace(np.log10(1.0 / (PERIOD_HIGH_HOURS * 3600)),
                            np.log10(1.0 / (PERIOD_LOW_HOURS * 3600)),
                            N_FREQS)
    periods_hours = 1.0 / freqs_hz / 3600.0

    # Compute everything first so we can share a global color scale.
    panels = []  # (treatment, sid, location, tag, ts_decim, power)
    global_lo, global_hi = np.inf, -np.inf
    for treatment, sid, location, tag in sensors:
        seg = per_sensor_series(df, sid)
        if seg is None:
            panels.append((treatment, sid, location, tag, None, None))
            continue
        ts, vals = seg
        power, was_cached = compute_tfr(sid, vals, freqs_hz)
        ts_decim = ts[::DECIM][:power.shape[1]]
        panels.append((treatment, sid, location, tag, ts_decim, power))
        global_lo = min(global_lo,
                         max(float(np.percentile(power, 2)), 1e-12))
        global_hi = max(global_hi, float(np.percentile(power, 99)))
        cache_tag = "cached" if was_cached else "computed"
        print(f"  {treatment:<7} @ {depth} cm  {sid} ({location}, {tag}): "
              f"{vals.size} samples  [{cache_tag}]")

    # Time axis = union of usable segments at this depth.
    valid_ts = [p[4] for p in panels if p[4] is not None]
    if not valid_ts:
        print(f"  no usable data at {depth} cm; skipping")
        return
    all_ts = np.concatenate(valid_ts)
    t0, t1 = all_ts.min(), all_ts.max()
    rain_ts, rain_vals = native_rain(df, t0, t1)

    # Layout: rain row (compact) + one row per sensor + a thin colorbar
    # column on the right that spans only the spectrogram rows.
    n_spec = len(panels)
    height_ratios = [0.6] + [1.0] * n_spec
    fig_h = 2.0 + 1.3 * n_spec       # taller per-row so the in-axes label fits
    fig = plt.figure(figsize=(15, fig_h))
    gs = GridSpec(1 + n_spec, 2,
                   height_ratios=height_ratios,
                   width_ratios=[60, 1],
                   figure=fig, hspace=0.12, wspace=0.02)
    fig.suptitle(
        f"Soil moisture spectrograms at {depth} cm — "
        f"wavelet={WAVELET}"
        + (f", n_cycles={N_CYCLES:.0f}" if WAVELET != "mexh" else "")
        + f", periods {PERIOD_LOW_HOURS} h – {PERIOD_HIGH_HOURS//24} d",
        fontsize=13, weight="bold")

    # --- Row 0: rain, native cadence -----------------------------------
    ax_rain = fig.add_subplot(gs[0, 0])
    if rain_ts.size:
        rain_floor = 0.05
        ax_rain.vlines(rain_ts,
                        rain_floor,
                        np.maximum(rain_vals, rain_floor * 1.01),
                        color="#1f77b4", linewidth=1.2)
        ax_rain.set_yscale("log")
        ax_rain.set_ylim(rain_floor, max(rain_vals) * 1.3)
    ax_rain.set_ylabel("Rain\n(mm/15 min, log)", fontsize=9)
    ax_rain.set_xlim(t0, t1)
    ax_rain.grid(axis="y", which="both", alpha=0.3)
    ax_rain.tick_params(labelbottom=False)
    ax_rain.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_rain.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))

    # --- Spectrogram rows -----------------------------------------------
    norm = LogNorm(vmin=global_lo, vmax=global_hi)
    cmap = "viridis"
    last_mesh = None
    spec_axes = []
    for i, (treatment, sid, location, tag, ts_decim, power) in enumerate(panels):
        ax = fig.add_subplot(gs[i + 1, 0], sharex=ax_rain)
        spec_axes.append(ax)
        # Label inside the axes with a white box so it's always legible
        # regardless of figure scaling. set_title at fontsize 10 was getting
        # squashed into the inter-row gap.
        label = (f"{treatment.upper()}  {location} «{tag}»  "
                 f"({sid}, {depth} cm)")
        if power is None:
            ax.text(0.5, 0.5, "no usable segment", ha="center", va="center",
                     transform=ax.transAxes, alpha=0.6)
            ax.text(0.005, 0.97, label, transform=ax.transAxes,
                     va="top", ha="left", fontsize=11, fontweight="bold",
                     color=TREATMENT_COLOR.get(treatment, "k"),
                     bbox=dict(boxstyle="round,pad=0.3",
                                facecolor="white", edgecolor="none",
                                alpha=0.85))
            continue
        p = np.clip(power, global_lo, None)
        mesh = ax.pcolormesh(ts_decim, periods_hours, p,
                              cmap=cmap, norm=norm, shading="auto")
        last_mesh = mesh
        ax.set_yscale("log")
        ax.text(0.005, 0.97, label, transform=ax.transAxes,
                 va="top", ha="left", fontsize=11, fontweight="bold",
                 color=TREATMENT_COLOR.get(treatment, "k"),
                 bbox=dict(boxstyle="round,pad=0.3",
                            facecolor="white", edgecolor="none",
                            alpha=0.85))
        ax.set_ylabel("Period (h)", fontsize=9)
        ax.yaxis.set_major_locator(mticker.LogLocator(base=10))
        ax.yaxis.set_minor_locator(
            mticker.LogLocator(base=10, subs=(2, 3, 5)))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%g"))
        for p_ref, txt in [(24, "24 h"), (24 * 7, "1 wk")]:
            if PERIOD_LOW_HOURS <= p_ref <= PERIOD_HIGH_HOURS:
                ax.axhline(p_ref, color="white", linestyle=":",
                            linewidth=0.7, alpha=0.6)

    # X-axis labels on the very bottom row only.
    if spec_axes:
        bottom = spec_axes[-1]
        bottom.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        bottom.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))
        bottom.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        bottom.tick_params(axis="x", which="major", length=6)
        bottom.tick_params(axis="x", which="minor", length=3)
        for ax in spec_axes[:-1]:
            ax.tick_params(labelbottom=False)

    # Colorbar — only spans spectrogram rows.
    if last_mesh is not None and len(spec_axes) >= 1:
        cax = fig.add_subplot(gs[1:, 1])
        cbar = fig.colorbar(last_mesh, cax=cax)
        cbar.set_label(r"Power ((m$^3$/m$^3$)$^2$, log)", fontsize=10)

    fig.autofmt_xdate()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print(f"Loading dataset (cached if available); WAVELET={WAVELET}…")
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )
    print(f"  {df.height:,} rows")

    for depth in DEPTHS_TO_PLOT:
        out = PLOTS / f"03_spectrogram_{depth}cm_{WAVELET}.png"
        print(f"Rendering {depth} cm → {out}")
        plot_for_depth(df, depth, out)
    print("Done.")


if __name__ == "__main__":
    main()
