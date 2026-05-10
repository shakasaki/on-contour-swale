"""Per-sensor rising-limb metrics for every detected event.

For every (event × sensor × depth) combination, characterise how the
sensor responded to the event:

    baseline:       median VWC in [event_start - BASELINE_HOURS, event_start]
    peak:           max VWC in   [event_start, event_start + PEAK_HOURS]
    Δ VWC:          peak − baseline
    t_to_peak:      peak time − event_start, in hours
    mean dVWC/dt:   Δ VWC / t_to_peak  (m³/m³ per hour)

A sensor is treated as "responding" to an event when Δ VWC ≥
``MIN_DELTA_VWC``. Non-responders are kept in the CSV with a
``responded=False`` flag so we can also count the "missed" rate per
treatment × depth — particularly relevant for swale 40 cm, which mostly
ignores rain.

Outputs:
    plots/rising_limb_metrics.csv
    plots/rising_limb_metrics.png   (boxplot grid)

Run from project root::

    .venv/bin/python scripts/01_rising_limb_metrics.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

BASELINE_HOURS = 2.0       # pre-event window for the baseline median
PEAK_HOURS = 24.0          # window after event_start in which to find the peak
MIN_DELTA_VWC = 0.005      # m³/m³ — minimum jump to count as "responded"

DEPTHS_TO_ANALYSE = [10, 40]

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("/home/alexis/DATA/swale")
METADATA = DATA_ROOT / "Metadata.xlsx"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

EVENTS_CSV   = PLOTS / "00_events_from_soil.csv"
METRICS_CSV  = PLOTS / "01_rising_limb_metrics.csv"
METRICS_PNG  = PLOTS / "01_rising_limb_metrics.png"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_events() -> pl.DataFrame:
    return pl.read_csv(
        EVENTS_CSV,
        schema_overrides={
            "start":     pl.Datetime("ns"),
            "end":       pl.Datetime("ns"),
            "peak_time": pl.Datetime("ns"),
        },
    )


def collect_traces(df: pl.DataFrame, depth_cm: int
                    ) -> dict[str, dict]:
    """Return {sensor_id: {ts, vals, treatment, location, tag}}."""
    sub = (df.filter((pl.col("variable") == "moisture")
                      & (pl.col("depth_cm") == depth_cm)
                      & pl.col("treatment").is_not_null()
                      & pl.col("value").is_not_null())
             .select(["sensor_id", "treatment", "location", "tag",
                       "timestamp", "value"])
             .sort(["sensor_id", "timestamp"]))
    out: dict[str, dict] = {}
    for sid, group in sub.group_by("sensor_id"):
        sid_str = str(sid[0]) if isinstance(sid, tuple) else str(sid)
        out[sid_str] = {
            "ts": group["timestamp"].to_numpy().astype("datetime64[ns]"),
            "vals": group["value"].to_numpy().astype(float),
            "treatment": group["treatment"][0],
            "location":  group["location"][0],
            "tag":       group["tag"][0],
        }
    return out


def measure_event(
    sensor: dict,
    event_start: np.datetime64,
) -> dict:
    """Compute the rising-limb metrics for one (sensor × event)."""
    ts, vals = sensor["ts"], sensor["vals"]
    t_pre = event_start - np.timedelta64(int(BASELINE_HOURS * 3600), "s")
    t_post = event_start + np.timedelta64(int(PEAK_HOURS * 3600), "s")

    pre_mask  = (ts >= t_pre) & (ts < event_start)
    post_mask = (ts >= event_start) & (ts <= t_post)

    base = float(np.nanmedian(vals[pre_mask])) if pre_mask.any() else float("nan")
    if not post_mask.any():
        return {
            "baseline_vwc": base, "peak_vwc": float("nan"),
            "delta_vwc": float("nan"), "t_to_peak_h": float("nan"),
            "mean_dvdt_per_h": float("nan"),
            "peak_time": np.datetime64("NaT", "ns"),
            "responded": False,
        }

    post_ts, post_v = ts[post_mask], vals[post_mask]
    i = int(np.nanargmax(post_v))
    peak = float(post_v[i])
    peak_ts = post_ts[i]
    delta = peak - base if np.isfinite(base) else float("nan")
    dt_h = float((peak_ts - event_start).astype("timedelta64[s]").astype(int)) / 3600.0
    mean_rate = (delta / dt_h) if (dt_h > 0 and np.isfinite(delta)) else float("nan")
    return {
        "baseline_vwc":   base,
        "peak_vwc":       peak,
        "delta_vwc":      delta,
        "t_to_peak_h":    dt_h,
        "mean_dvdt_per_h": mean_rate,
        "peak_time":      peak_ts,
        "responded":      bool(np.isfinite(delta) and delta >= MIN_DELTA_VWC),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_metrics(df: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict] = []
    starts = events["start"].to_numpy().astype("datetime64[ns]")
    event_ids = events["event"].to_numpy()
    for depth in DEPTHS_TO_ANALYSE:
        sensors = collect_traces(df, depth)
        for sid, meta in sensors.items():
            for ev_id, ev_start in zip(event_ids, starts):
                m = measure_event(meta, ev_start)
                rows.append({
                    "event":       int(ev_id),
                    "event_start": ev_start,
                    "sensor_id":   sid,
                    "treatment":   meta["treatment"],
                    "location":    meta["location"],
                    "tag":         meta["tag"],
                    "depth_cm":    depth,
                    **m,
                })
    return pl.from_dicts(rows)


def plot_distributions(metrics: pl.DataFrame, out: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    palette = {"swale": "#1f77b4", "control": "#d62728"}
    metric_specs = [
        ("delta_vwc",       "Δ VWC (peak − baseline)\n(m³/m³)"),
        ("t_to_peak_h",     "Time to peak\n(h)"),
        ("mean_dvdt_per_h", "Mean dVWC/dt during rise\n(m³/m³ per h)"),
    ]
    treatments = ["swale", "control"]
    fig, axes = plt.subplots(3, len(DEPTHS_TO_ANALYSE),
                              figsize=(4.5 * len(DEPTHS_TO_ANALYSE), 9),
                              sharey="row")
    if axes.ndim == 1:
        axes = axes[:, None]

    responders = metrics.filter(pl.col("responded"))

    for col_i, depth in enumerate(DEPTHS_TO_ANALYSE):
        for row_i, (col, ylabel) in enumerate(metric_specs):
            ax = axes[row_i, col_i]
            data = []
            for treat in treatments:
                vals = (responders
                        .filter((pl.col("depth_cm") == depth)
                                  & (pl.col("treatment") == treat))
                        [col].drop_nulls().to_numpy())
                vals = vals[np.isfinite(vals)]
                data.append(vals)
            bp = ax.boxplot(data, tick_labels=treatments, widths=0.6,
                              showfliers=False, patch_artist=True)
            for patch, treat in zip(bp["boxes"], treatments):
                patch.set_facecolor(palette[treat])
                patch.set_alpha(0.5)
            for med in bp["medians"]:
                med.set_color("k")
            for j, vals in enumerate(data, start=1):
                if vals.size:
                    jitter = (np.random.default_rng(0).uniform(-0.15, 0.15, vals.size))
                    ax.scatter(np.full_like(vals, j) + jitter, vals,
                                color="k", s=2, alpha=0.4)
            ax.set_ylabel(ylabel if col_i == 0 else "")
            if row_i == 0:
                full = metrics.filter(pl.col("depth_cm") == depth)
                rate = {t: float(full.filter(pl.col("treatment") == t)
                                       ["responded"].mean() or 0)
                        for t in treatments}
                hdr = (f"{depth} cm  •  responded: "
                        f"sw={rate['swale']*100:.0f}%, "
                        f"ct={rate['control']*100:.0f}%")
                ax.set_title(hdr, fontsize=10, weight="bold")

    fig.suptitle(f"Rising-limb metrics by treatment × depth "
                  f"(events from {EVENTS_CSV.name}; "
                  f"only responders shown; Δ VWC ≥ {MIN_DELTA_VWC})",
                  fontsize=11, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def print_summary(metrics: pl.DataFrame) -> None:
    print("\nResponder summary (responded = Δ VWC ≥ "
          f"{MIN_DELTA_VWC} m³/m³):")
    summary = (metrics.group_by(["depth_cm", "treatment"])
                       .agg([
                           pl.len().alias("n_total"),
                           pl.col("responded").sum().alias("n_resp"),
                           pl.col("delta_vwc").filter(pl.col("responded"))
                              .median().alias("median_dvwc"),
                           pl.col("t_to_peak_h").filter(pl.col("responded"))
                              .median().alias("median_tpeak_h"),
                           pl.col("mean_dvdt_per_h").filter(pl.col("responded"))
                              .median().alias("median_rate"),
                       ])
                       .sort(["depth_cm", "treatment"]))
    print(summary)


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    print("Loading dataset (cached if available)…")
    df = load_swale_dataset(
        data_root=DATA_ROOT,
        metadata_xlsx=METADATA,
        cache_dir=CACHE,
        grid="none",
    )
    events = load_events()
    print(f"  {events.height} events from {EVENTS_CSV.name}")

    print("Computing rising-limb metrics…")
    metrics = compute_metrics(df, events)
    metrics.write_csv(METRICS_CSV)
    print(f"  wrote {METRICS_CSV.relative_to(ROOT)} ({metrics.height:,} rows)")

    print_summary(metrics)
    plot_distributions(metrics, METRICS_PNG)
    print(f"  wrote {METRICS_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
