"""Wetting-front lag: how long after 10 cm wets does 40 cm respond?

For every event and every *location* that has both a 10 cm and a 40 cm
sensor, measure:

    onset_10:    first sample where VWC > (pre-event median + ONSET_THRESHOLD)
                 in [event_start − 0, event_start + POST_HOURS]
    onset_40:    same, on the 40 cm trace at the same location
    onset_lag:   onset_40 − onset_10  (NaN if 40 cm never crosses)
    peak_lag:    peak_40 − peak_10    (NaN if 40 cm never responds)

The interesting question — and the prior finding the user flagged — is
that swale 40 cm sits at 0.05–0.10 m³/m³ and rarely responds. This
script makes the "doesn't respond" rate explicit per treatment, alongside
the lag distribution conditional on having responded.

Outputs:
    plots/wetting_front_lag.csv
    plots/wetting_front_lag.png

Run from project root::

    .venv/bin/python scripts/03_wetting_front_lag.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns

from swale.config import load_settings
from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

BASELINE_HOURS = 2.0       # pre-event baseline window
ONSET_THRESHOLD = 0.005    # m³/m³ — same as Δ VWC responder threshold (script 01)
PRE_HOURS = 1.0            # context shown in plot
POST_HOURS = 72.0          # search window for onset and peak
DEPTH_SHALLOW = 10
DEPTH_DEEP = 40

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = load_settings()
DATA_ROOT = SETTINGS.data_root
METADATA = SETTINGS.metadata_xlsx
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

EVENTS_CSV = PLOTS / "00_events_from_soil.csv"
LAG_CSV    = PLOTS / "06_wetting_front_lag.csv"
LAG_PNG    = PLOTS / "06_wetting_front_lag.png"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_events() -> pl.DataFrame:
    return pl.read_csv(
        EVENTS_CSV,
        schema_overrides={"start": pl.Datetime("ns"),
                           "end":   pl.Datetime("ns"),
                           "peak_time": pl.Datetime("ns")},
    )


def collect_paired_traces(df: pl.DataFrame) -> dict[str, dict]:
    """Return {location: {treatment, shallow:{ts,vals,sid}, deep:{ts,vals,sid}}}.

    Only includes locations that have both a 10 cm and a 40 cm moisture
    sensor with a recognised treatment.
    """
    sub = (df.filter((pl.col("variable") == "moisture")
                      & pl.col("treatment").is_not_null()
                      & pl.col("depth_cm").is_in([DEPTH_SHALLOW, DEPTH_DEEP])
                      & pl.col("value").is_not_null())
             .select(["location", "treatment", "depth_cm",
                       "sensor_id", "tag", "timestamp", "value"])
             .sort(["location", "depth_cm", "timestamp"]))

    pairs: dict[str, dict] = {}
    for (loc,), group in sub.group_by(["location"], maintain_order=True):
        loc = str(loc)
        depths = group["depth_cm"].unique().to_list()
        if DEPTH_SHALLOW not in depths or DEPTH_DEEP not in depths:
            continue
        treat = group["treatment"][0]
        rec = {"treatment": treat, "shallow": None, "deep": None}
        for depth, slot in ((DEPTH_SHALLOW, "shallow"), (DEPTH_DEEP, "deep")):
            g = group.filter(pl.col("depth_cm") == depth).sort("timestamp")
            rec[slot] = {
                "sid":  g["sensor_id"][0],
                "tag":  g["tag"][0],
                "ts":   g["timestamp"].to_numpy().astype("datetime64[ns]"),
                "vals": g["value"].to_numpy().astype(float),
            }
        pairs[loc] = rec
    return pairs


def first_crossing_h(ts: np.ndarray, vals: np.ndarray,
                      event_start: np.datetime64,
                      threshold_above_baseline: float) -> float:
    """Hours from event_start to first sample whose VWC exceeds baseline + thr.

    Returns ``np.nan`` if no crossing in the post-event window.
    """
    t_pre = event_start - np.timedelta64(int(BASELINE_HOURS * 3600), "s")
    t_post = event_start + np.timedelta64(int(POST_HOURS * 3600), "s")
    pre_mask = (ts >= t_pre) & (ts < event_start)
    if not pre_mask.any():
        return float("nan")
    base = float(np.nanmedian(vals[pre_mask]))
    if not np.isfinite(base):
        return float("nan")

    post_mask = (ts >= event_start) & (ts <= t_post)
    pt = ts[post_mask]
    pv = vals[post_mask]
    above = pv > (base + threshold_above_baseline)
    if not above.any():
        return float("nan")
    i = int(np.argmax(above))
    return float((pt[i] - event_start).astype("timedelta64[s]").astype(int)) / 3600.0


def peak_h(ts: np.ndarray, vals: np.ndarray,
            event_start: np.datetime64) -> float:
    """Hours from event_start to the post-event peak. NaN if no data."""
    t_post = event_start + np.timedelta64(int(POST_HOURS * 3600), "s")
    mask = (ts >= event_start) & (ts <= t_post)
    if not mask.any():
        return float("nan")
    pt = ts[mask]
    pv = vals[mask]
    if np.isnan(pv).all():
        return float("nan")
    i = int(np.nanargmax(pv))
    return float((pt[i] - event_start).astype("timedelta64[s]").astype(int)) / 3600.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_lags(df: pl.DataFrame, events: pl.DataFrame) -> pl.DataFrame:
    pairs = collect_paired_traces(df)
    rows: list[dict] = []
    starts = events["start"].to_numpy().astype("datetime64[ns]")
    event_ids = events["event"].to_numpy()
    for loc, rec in pairs.items():
        sh, de = rec["shallow"], rec["deep"]
        for ev_id, ev_start in zip(event_ids, starts):
            on10 = first_crossing_h(sh["ts"], sh["vals"], ev_start, ONSET_THRESHOLD)
            on40 = first_crossing_h(de["ts"], de["vals"], ev_start, ONSET_THRESHOLD)
            pk10 = peak_h(sh["ts"], sh["vals"], ev_start)
            pk40 = peak_h(de["ts"], de["vals"], ev_start)
            onset_lag = (on40 - on10) if (np.isfinite(on10) and np.isfinite(on40)) else float("nan")
            peak_lag  = (pk40 - pk10) if (np.isfinite(pk10) and np.isfinite(pk40)) else float("nan")
            rows.append({
                "event":           int(ev_id),
                "event_start":     ev_start,
                "location":        loc,
                "treatment":       rec["treatment"],
                "sensor_10":       sh["sid"],
                "sensor_40":       de["sid"],
                "onset_10_h":      on10,
                "onset_40_h":      on40,
                "onset_lag_h":     onset_lag,
                "peak_10_h":       pk10,
                "peak_40_h":       pk40,
                "peak_lag_h":      peak_lag,
                "responded_40":    np.isfinite(on40),
            })
    return pl.from_dicts(rows).with_columns(
        pl.col("responded_40").cast(pl.Boolean)
    )


def plot_lag_distributions(lags: pl.DataFrame, out: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    palette = {"swale": "#1f77b4", "control": "#d62728"}
    treatments = ["swale", "control"]

    # Only consider events where the 10 cm sensor itself responded — otherwise
    # there is no front to track. Crossing in shallow == event with finite onset_10.
    base = lags.filter(pl.col("onset_10_h").is_finite())

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    ax_resp, ax_onset, ax_peak = axes

    # Response rate at 40 cm | shallow responded.
    rates = []
    counts = []
    for treat in treatments:
        sub = base.filter(pl.col("treatment") == treat)
        n_total = sub.height
        n_resp  = sub.filter(pl.col("responded_40")).height
        rate = (n_resp / n_total) if n_total else 0
        rates.append(rate)
        counts.append((n_resp, n_total))
    bars = ax_resp.bar(treatments, rates,
                         color=[palette[t] for t in treatments], alpha=0.7)
    for bar, (nr, nt), rate in zip(bars, counts, rates):
        ax_resp.text(bar.get_x() + bar.get_width() / 2,
                      rate + 0.02, f"{nr}/{nt}\n({rate*100:.0f}%)",
                      ha="center", va="bottom", fontsize=9)
    ax_resp.set_ylim(0, 1.05)
    ax_resp.set_ylabel("Fraction of events where 40 cm crossed onset",
                        fontsize=10)
    ax_resp.set_title("40 cm response rate", fontsize=11, weight="bold")

    # Onset lag distribution (only when 40 cm responded).
    for ax, col, title in (
        (ax_onset, "onset_lag_h", "Onset lag (40 cm − 10 cm)"),
        (ax_peak,  "peak_lag_h",  "Peak lag (40 cm − 10 cm)"),
    ):
        data = []
        for treat in treatments:
            v = (base.filter((pl.col("treatment") == treat)
                              & pl.col(col).is_finite())
                       [col].to_numpy())
            data.append(v)
        bp = ax.boxplot(data, tick_labels=treatments, widths=0.6,
                          showfliers=False, patch_artist=True)
        for patch, treat in zip(bp["boxes"], treatments):
            patch.set_facecolor(palette[treat])
            patch.set_alpha(0.5)
        for med in bp["medians"]:
            med.set_color("k")
        for j, vals in enumerate(data, start=1):
            if vals.size:
                jitter = np.random.default_rng(0).uniform(-0.15, 0.15, vals.size)
                ax.scatter(np.full_like(vals, j) + jitter, vals,
                            color="k", s=2, alpha=0.4)
        ax.axhline(0, color="k", ls=":", lw=0.6, alpha=0.5)
        ax.set_ylabel("hours")
        ax.set_title(title, fontsize=11, weight="bold")

    fig.suptitle("10 cm → 40 cm wetting-front lag, conditioned on 10 cm having responded",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def print_summary(lags: pl.DataFrame) -> None:
    print("\nPaired locations:")
    locs = (lags.select(["location", "treatment",
                          "sensor_10", "sensor_40"])
                  .unique()
                  .sort(["treatment", "location"]))
    print(locs)

    base = lags.filter(pl.col("onset_10_h").is_finite())
    print(f"\nEvents with a 10 cm onset: {base.height} of {lags.height} (location × event) pairs")

    summary = (base.group_by("treatment")
                    .agg([
                        pl.len().alias("n_pairs"),
                        pl.col("responded_40").sum().alias("n_40_resp"),
                        pl.col("onset_lag_h").filter(pl.col("onset_lag_h").is_finite())
                           .median().alias("median_onset_lag_h"),
                        pl.col("peak_lag_h").filter(pl.col("peak_lag_h").is_finite())
                           .median().alias("median_peak_lag_h"),
                    ])
                    .sort("treatment"))
    print("\nLag summary (only events where 10 cm responded):")
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

    print("Computing wetting-front lags…")
    lags = compute_lags(df, events)
    lags.write_csv(LAG_CSV)
    print(f"  wrote {LAG_CSV.relative_to(ROOT)} ({lags.height:,} rows)")

    print_summary(lags)
    plot_lag_distributions(lags, LAG_PNG)
    print(f"\n  wrote {LAG_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
