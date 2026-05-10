"""Recession-tail fits: exponential vs power-law per (event × sensor).

After a wetting event the soil moisture relaxes back toward equilibrium
through some combination of vertical drainage, lateral flow, and
evapotranspiration. The two simplest functional forms are:

    exponential:  VWC(t) = A · exp(−t/τ) + C
    power-law:    VWC(t) = A · (t − t_peak)^(−α) + C

Exponential dominates when relaxation is dominated by a single first-
order loss process (linear reservoir). Power-law arises naturally when
the recession integrates over a distribution of pore-scale drainage
timescales, or when the underlying flow is a non-linear function of
storage (e.g. Boussinesq with α=1 → free drainage with α≈0.5–2 depending
on aquifer geometry). Comparing both fits per event therefore says
something about whether the swale is acting like a single-pool linear
reservoir or like a heterogeneous, slow-tailed system.

Per (event × sensor):
    1. Identify recession start (= peak time within
       [event_start, event_start + PEAK_SEARCH_HOURS]).
    2. Recession end = next event start − GUARD_HOURS, capped at
       MAX_TAIL_HOURS.
    3. Fit both functional forms with non-linear least squares; compute
       R² for each.

Outputs:
    plots/recession_fits.csv         — one row per (event × sensor).
    plots/recession_fits_dist.png    — distribution of τ, α, R² across treatment×depth.
    plots/recession_fits_examples.png — a few example tails with both fits overlaid.

Run from project root::

    .venv/bin/python scripts/04_recession_fits.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from scipy.optimize import curve_fit

from swale.loader import load_swale_dataset

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

PEAK_SEARCH_HOURS = 24.0       # search for peak within this window after event_start
GUARD_HOURS = 2.0              # stop recession this long before next event_start
MAX_TAIL_HOURS = 7 * 24.0      # cap recession window at 7 days
MIN_TAIL_HOURS = 12.0          # require ≥ 12 h of tail to attempt a fit
MIN_DELTA_VWC = 0.005          # peak must clear baseline by this much
DEPTHS_TO_FIT = [10, 40]

EXP_INIT = (0.05, 24.0, 0.10)              # (A, τ_h, C)
POW_EPS_HOURS = 0.25                        # avoid t=0 singularity in power-law
POW_INIT = (0.05, 0.5, 0.10)                # (A, α, C)

N_EXAMPLES = 6                              # number of example tails to plot

# Representative-events plot — full event windows showing the slow-drainage
# swale signature alongside control.
N_REPRESENTATIVE = 3                        # number of events to highlight
REP_PRE_HOURS = 6.0                         # window context before event_start
REP_POST_HOURS = 168.0                      # 7-day post-event window

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("/home/alexis/DATA/swale")
METADATA = DATA_ROOT / "Metadata.xlsx"
CACHE = ROOT / "cache"
PLOTS = ROOT / "plots"

EVENTS_CSV   = PLOTS / "00_events_from_soil.csv"
FIT_CSV      = PLOTS / "04_recession_fits.csv"
DIST_PNG     = PLOTS / "04_recession_fits_distributions.png"
EXAMPLES_PNG = PLOTS / "04_recession_fits_examples.png"
REPRESENTATIVE_PNG = PLOTS / "04_recession_representative_events.png"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_events() -> pl.DataFrame:
    return pl.read_csv(
        EVENTS_CSV,
        schema_overrides={"start": pl.Datetime("ns"),
                           "end":   pl.Datetime("ns"),
                           "peak_time": pl.Datetime("ns")},
    ).sort("start")


def collect_traces(df: pl.DataFrame) -> dict[tuple[int, str], dict]:
    """Return {(depth, sensor_id): {ts, vals, treatment, location, tag}}."""
    sub = (df.filter((pl.col("variable") == "moisture")
                      & pl.col("treatment").is_not_null()
                      & pl.col("depth_cm").is_in(DEPTHS_TO_FIT)
                      & pl.col("value").is_not_null())
             .select(["sensor_id", "treatment", "location", "tag",
                       "depth_cm", "timestamp", "value"])
             .sort(["sensor_id", "timestamp"]))
    out: dict[tuple[int, str], dict] = {}
    for (sid, depth), g in sub.group_by(["sensor_id", "depth_cm"]):
        out[(int(depth), str(sid))] = {
            "ts":   g["timestamp"].to_numpy().astype("datetime64[ns]"),
            "vals": g["value"].to_numpy().astype(float),
            "treatment": g["treatment"][0],
            "location":  g["location"][0],
            "tag":       g["tag"][0],
        }
    return out


def exp_model(t_h: np.ndarray, A: float, tau_h: float, C: float) -> np.ndarray:
    return A * np.exp(-t_h / tau_h) + C


def pow_model(t_h: np.ndarray, A: float, alpha: float, C: float) -> np.ndarray:
    return A * np.power(t_h + POW_EPS_HOURS, -alpha) + C


def r_squared(y_obs: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_obs - y_pred) ** 2)
    ss_tot = np.sum((y_obs - np.mean(y_obs)) ** 2)
    if ss_tot <= 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def fit_one_tail(t_h: np.ndarray, vwc: np.ndarray) -> dict:
    """Fit both models to a single recession tail and return parameters + R²."""
    out = {
        "exp_A": np.nan, "exp_tau_h": np.nan, "exp_C": np.nan, "exp_r2": np.nan,
        "pow_A": np.nan, "pow_alpha": np.nan, "pow_C": np.nan, "pow_r2": np.nan,
    }
    if t_h.size < 4:
        return out

    # Bounds keep the optimiser physical: A>=0, τ≥0.5h, α∈[0,3], C∈[0,0.6].
    try:
        popt, _ = curve_fit(exp_model, t_h, vwc, p0=EXP_INIT,
                              bounds=([0, 0.5, 0.0],
                                       [np.inf, 1e4, 0.6]),
                              maxfev=5000)
        out["exp_A"], out["exp_tau_h"], out["exp_C"] = popt
        out["exp_r2"] = r_squared(vwc, exp_model(t_h, *popt))
    except (RuntimeError, ValueError):
        pass

    try:
        popt, _ = curve_fit(pow_model, t_h, vwc, p0=POW_INIT,
                              bounds=([0, 0.0, 0.0],
                                       [np.inf, 3.0, 0.6]),
                              maxfev=5000)
        out["pow_A"], out["pow_alpha"], out["pow_C"] = popt
        out["pow_r2"] = r_squared(vwc, pow_model(t_h, *popt))
    except (RuntimeError, ValueError):
        pass

    return out


def extract_tail(
    sensor_data: dict,
    event_start: np.datetime64,
    next_event_start: np.datetime64 | None,
) -> dict | None:
    """Pull the recession segment for one (event × sensor). Return None if too short."""
    ts, vals = sensor_data["ts"], sensor_data["vals"]

    # 1. Locate peak in [event_start, event_start + PEAK_SEARCH_HOURS].
    peak_window_end = event_start + np.timedelta64(int(PEAK_SEARCH_HOURS * 3600), "s")
    peak_mask = (ts >= event_start) & (ts <= peak_window_end)
    if not peak_mask.any():
        return None
    peak_ts_arr = ts[peak_mask]
    peak_v_arr = vals[peak_mask]
    if np.isnan(peak_v_arr).all():
        return None
    peak_i = int(np.nanargmax(peak_v_arr))
    peak_ts = peak_ts_arr[peak_i]
    peak_vwc = float(peak_v_arr[peak_i])

    # 2. Pre-event baseline for the responder gate.
    base_start = event_start - np.timedelta64(int(2 * 3600), "s")
    base_mask  = (ts >= base_start) & (ts < event_start)
    base = float(np.nanmedian(vals[base_mask])) if base_mask.any() else float("nan")
    delta = peak_vwc - base if np.isfinite(base) else float("nan")
    if not (np.isfinite(delta) and delta >= MIN_DELTA_VWC):
        return None

    # 3. Recession end = next event − guard, capped at MAX_TAIL_HOURS.
    tail_end = peak_ts + np.timedelta64(int(MAX_TAIL_HOURS * 3600), "s")
    if next_event_start is not None:
        guarded = next_event_start - np.timedelta64(int(GUARD_HOURS * 3600), "s")
        if guarded < tail_end:
            tail_end = guarded
    if tail_end <= peak_ts:
        return None

    tail_mask = (ts > peak_ts) & (ts <= tail_end)
    if not tail_mask.any():
        return None
    t_abs = ts[tail_mask]
    v = vals[tail_mask]
    finite = ~np.isnan(v)
    t_abs = t_abs[finite]
    v = v[finite]
    if v.size < 4:
        return None

    # Hours since peak.
    t_h = (t_abs - peak_ts).astype("timedelta64[s]").astype(np.int64) / 3600.0
    if (t_h[-1] - t_h[0]) < MIN_TAIL_HOURS:
        return None

    return {
        "peak_ts":  peak_ts,
        "peak_vwc": peak_vwc,
        "t_h":      t_h,
        "vwc":      v,
    }


def fit_all(
    df: pl.DataFrame,
    events: pl.DataFrame,
) -> tuple[pl.DataFrame, list[dict]]:
    """Run fits, return (results_frame, list_of_example_segments)."""
    traces = collect_traces(df)
    starts = events["start"].to_numpy().astype("datetime64[ns]")
    next_starts = np.concatenate([starts[1:], np.array(["2099-01-01"], dtype="datetime64[ns]")])
    event_ids = events["event"].to_numpy()

    rows: list[dict] = []
    examples: list[dict] = []

    for (depth, sid), sensor in traces.items():
        for ev_id, ev_start, next_start in zip(event_ids, starts, next_starts):
            tail = extract_tail(sensor, ev_start, next_start)
            if tail is None:
                continue
            fit = fit_one_tail(tail["t_h"], tail["vwc"])
            row = {
                "event":      int(ev_id),
                "event_start": ev_start,
                "depth_cm":   depth,
                "sensor_id":  sid,
                "treatment":  sensor["treatment"],
                "location":   sensor["location"],
                "tag":        sensor["tag"],
                "peak_time":  tail["peak_ts"],
                "peak_vwc":   tail["peak_vwc"],
                "tail_hours": float(tail["t_h"][-1] - tail["t_h"][0]),
                "n_samples":  int(tail["vwc"].size),
                **fit,
            }
            rows.append(row)
            examples.append({**row, "_t_h": tail["t_h"], "_vwc": tail["vwc"]})

    frame = pl.from_dicts(rows)
    return frame, examples


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def plot_distributions(fits: pl.DataFrame, out: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper")
    palette = {"swale": "#1f77b4", "control": "#d62728"}
    treatments = ["swale", "control"]

    metric_specs = [
        ("exp_tau_h", "Exp. τ (h)"),
        ("pow_alpha", "Power-law α"),
        ("exp_r2",    "Exp. R²"),
        ("pow_r2",    "Power-law R²"),
    ]

    fig, axes = plt.subplots(len(metric_specs), len(DEPTHS_TO_FIT),
                              figsize=(4.5 * len(DEPTHS_TO_FIT),
                                        2.8 * len(metric_specs)),
                              sharey="row")
    if axes.ndim == 1:
        axes = axes[:, None]

    for col_i, depth in enumerate(DEPTHS_TO_FIT):
        for row_i, (col, ylabel) in enumerate(metric_specs):
            ax = axes[row_i, col_i]
            data = []
            for treat in treatments:
                v = (fits.filter((pl.col("depth_cm") == depth)
                                   & (pl.col("treatment") == treat))
                          [col].drop_nulls().to_numpy())
                v = v[np.isfinite(v)]
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
            ax.set_ylabel(ylabel if col_i == 0 else "")
            if row_i == 0:
                ax.set_title(f"{depth} cm", fontsize=11, weight="bold")

    fig.suptitle("Recession-tail fits — exponential vs power-law",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def plot_examples(examples: list[dict], out: Path) -> None:
    """Plot a handful of recession tails with both fits overlaid.

    Stratified pick: best-R² exp fits in each (depth × treatment) cell so
    the user sees the algorithm performing in regimes where it should.
    """
    sns.set_theme(style="whitegrid", context="paper")
    if not examples:
        return

    # Index examples by (depth, treatment); pick top-N_EXAMPLES by exp R².
    by_cell: dict[tuple[int, str], list[dict]] = {}
    for ex in examples:
        if not np.isfinite(ex["exp_r2"]):
            continue
        by_cell.setdefault((ex["depth_cm"], ex["treatment"]), []).append(ex)
    for k in by_cell:
        by_cell[k].sort(key=lambda e: e["exp_r2"], reverse=True)

    cells = [(d, t) for d in DEPTHS_TO_FIT for t in ("swale", "control")]
    n_cols = len(cells)
    fig, axes = plt.subplots(1, n_cols, figsize=(3.5 * n_cols, 4),
                              sharey=False)
    if n_cols == 1:
        axes = [axes]

    for ax, (depth, treat) in zip(axes, cells):
        pool = by_cell.get((depth, treat), [])
        if not pool:
            ax.set_title(f"{depth} cm  •  {treat}\n(no fits)", fontsize=10)
            continue
        ex = pool[0]
        t_h = ex["_t_h"]
        v = ex["_vwc"]
        ax.scatter(t_h, v, s=6, color="0.3", label="data")
        t_grid = np.linspace(t_h.min(), t_h.max(), 200)
        if np.isfinite(ex["exp_tau_h"]):
            ax.plot(t_grid,
                     exp_model(t_grid, ex["exp_A"], ex["exp_tau_h"], ex["exp_C"]),
                     color="#1f77b4", lw=1.5,
                     label=f"exp τ={ex['exp_tau_h']:.1f}h R²={ex['exp_r2']:.2f}")
        if np.isfinite(ex["pow_alpha"]):
            ax.plot(t_grid,
                     pow_model(t_grid, ex["pow_A"], ex["pow_alpha"], ex["pow_C"]),
                     color="#d62728", lw=1.5, ls="--",
                     label=f"pow α={ex['pow_alpha']:.2f} R²={ex['pow_r2']:.2f}")
        ax.set_xlabel("hours since peak")
        ax.set_ylabel("VWC (m³/m³)")
        ax.set_title(f"{depth} cm  •  {treat}\n{ex['sensor_id']}  "
                      f"event {ex['event']}", fontsize=10)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle("Recession examples — best exp-R² fit per (depth × treatment)",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def pick_representative_events(fits: pl.DataFrame,
                                  events: pl.DataFrame,
                                  n: int = N_REPRESENTATIVE) -> list[int]:
    """Select n event_ids whose fits are clean *and* whose response is large.

    The first cut of this function ranked by τ_swale/τ_control and ended up
    showcasing edge-case fits with τ values in the thousands of hours. We
    instead prefer events that are big and fit well, and let the visible
    swale-control contrast speak for itself.

    Selection:
      * At 10 cm: ≥3 swale sensors and ≥2 control sensors with finite,
        physical-range exp-τ (5–500 h) and exp-R² ≥ 0.7.
      * At 40 cm: ≥1 sensor per treatment fit (looser — 40 cm is harder).
      * Rank by total per-event peak excursion (sum of A across sensors at
        10 cm), so the row showcases events that actually wet the soil.
    """
    f10 = fits.filter((pl.col("depth_cm") == 10)
                       & pl.col("exp_tau_h").is_between(5, 500)
                       & (pl.col("exp_r2") >= 0.7))
    f40 = fits.filter((pl.col("depth_cm") == 40)
                       & pl.col("exp_tau_h").is_finite())

    counts10 = (f10.group_by(["event", "treatment"])
                     .agg(pl.len().alias("n_sensors"))
                     .pivot(values="n_sensors", index="event", on="treatment")
                     .rename({"swale": "n_sw_10", "control": "n_ct_10"},
                              strict=False))
    counts40 = (f40.group_by(["event", "treatment"])
                     .agg(pl.len().alias("n_sensors"))
                     .pivot(values="n_sensors", index="event", on="treatment")
                     .rename({"swale": "n_sw_40", "control": "n_ct_40"},
                              strict=False))

    needed = ["n_sw_10", "n_ct_10", "n_sw_40", "n_ct_40"]
    counts = counts10.join(counts40, on="event", how="full", coalesce=True)
    for c in needed:
        if c not in counts.columns:
            return []
        counts = counts.with_columns(pl.col(c).fill_null(0))

    # Magnitude proxy: sum of fitted A at 10 cm (each sensor's recession amplitude).
    mags = (f10.group_by("event")
                 .agg(pl.col("exp_A").sum().alias("mag")))

    ranked = (
        counts.filter((pl.col("n_sw_10") >= 3) & (pl.col("n_ct_10") >= 2)
                        & (pl.col("n_sw_40") >= 1) & (pl.col("n_ct_40") >= 1))
                .join(mags, on="event", how="inner")
                .sort("mag", descending=True)
    )
    return ranked["event"].head(n).to_list()


def plot_representative_events(
    df: pl.DataFrame,
    events: pl.DataFrame,
    fits: pl.DataFrame,
    out: Path,
) -> None:
    """For a few well-fit events, overlay all sensor traces from event_start
    through 7 days, comparing swale vs control side-by-side at 10 and 40 cm.
    """
    sns.set_theme(style="whitegrid", context="paper")

    chosen = pick_representative_events(fits, events, n=N_REPRESENTATIVE)
    if not chosen:
        print("  (no representative events satisfied selection criteria)")
        return

    traces = collect_traces(df)              # (depth, sensor_id) → trace dict
    starts_arr = events["start"].to_numpy().astype("datetime64[ns]")
    event_ids  = events["event"].to_numpy()
    start_for = {int(e): s for e, s in zip(event_ids, starts_arr)}

    palette = {"swale": "#1f77b4", "control": "#d62728"}
    n_rows = len(chosen)
    n_cols = len(DEPTHS_TO_FIT)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(6 * n_cols, 3.0 * n_rows),
                              sharey="col")
    if n_rows == 1:
        axes = axes[None, :]

    for row_i, ev_id in enumerate(chosen):
        ev_start = start_for[ev_id]
        t0 = ev_start - np.timedelta64(int(REP_PRE_HOURS * 3600), "s")
        t1 = ev_start + np.timedelta64(int(REP_POST_HOURS * 3600), "s")

        for col_i, depth in enumerate(DEPTHS_TO_FIT):
            ax = axes[row_i, col_i]
            for (d, sid), tr in traces.items():
                if d != depth:
                    continue
                ts = tr["ts"]
                vals = tr["vals"]
                mask = (ts >= t0) & (ts <= t1)
                if not mask.any():
                    continue
                hours = ((ts[mask] - ev_start).astype("timedelta64[s]")
                          .astype(np.int64) / 3600.0)
                ax.plot(hours, vals[mask],
                         color=palette[tr["treatment"]],
                         lw=1.0, alpha=0.7,
                         label=f"{tr['treatment'][:2]}-{tr['tag']} ({sid})")
            ax.axvline(0, color="k", ls=":", lw=0.8, alpha=0.5)
            ax.set_xlim(-REP_PRE_HOURS, REP_POST_HOURS)
            ax.grid(alpha=0.3)
            if row_i == n_rows - 1:
                ax.set_xlabel("Hours since event start")
            if col_i == 0:
                ax.set_ylabel(f"Event {ev_id}\n{ev_start.astype('datetime64[D]')}\n"
                                f"VWC (m³/m³)")

            # τ annotation per treatment in this cell, if available.
            cell = (fits.filter((pl.col("event") == ev_id)
                                  & (pl.col("depth_cm") == depth)
                                  & pl.col("exp_tau_h").is_finite())
                          .group_by("treatment")
                          .agg(pl.col("exp_tau_h").median().alias("tau_h")))
            tau_txt = []
            for treat in ("swale", "control"):
                t = cell.filter(pl.col("treatment") == treat)
                if t.height:
                    tau_txt.append(f"{treat[:2]}-τ={t['tau_h'][0]:.0f}h")
            if tau_txt:
                ax.text(0.97, 0.95, "  ".join(tau_txt),
                          transform=ax.transAxes,
                          ha="right", va="top", fontsize=9,
                          bbox=dict(boxstyle="round,pad=0.3",
                                     facecolor="white", alpha=0.85, lw=0))

            if row_i == 0:
                ax.set_title(f"{depth} cm", fontsize=11, weight="bold")

        # Single per-row legend on the rightmost panel.
        axes[row_i, -1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                                  fontsize=7, frameon=False)

    fig.suptitle("Representative events — swale vs control wetting and recession\n"
                  f"(events ranked by 10 cm response magnitude, "
                  f"with τ ∈ [5, 500] h and R² ≥ 0.7; "
                  f"window = −{REP_PRE_HOURS:g} h to +{REP_POST_HOURS/24:g} d)",
                  fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0, 0.88, 0.94))
    fig.savefig(out, dpi=130)
    plt.close(fig)


def print_summary(fits: pl.DataFrame) -> None:
    summary = (fits.group_by(["depth_cm", "treatment"])
                    .agg([
                        pl.len().alias("n_fits"),
                        pl.col("exp_tau_h").median().alias("median_tau_h"),
                        pl.col("exp_r2").median().alias("median_exp_r2"),
                        pl.col("pow_alpha").median().alias("median_alpha"),
                        pl.col("pow_r2").median().alias("median_pow_r2"),
                    ])
                    .sort(["depth_cm", "treatment"]))
    print("\nFit summary:")
    print(summary)


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
    events = load_events()
    print(f"  {events.height} events from {EVENTS_CSV.name}")

    print("Fitting recession tails (exp + power-law)…")
    fits, examples = fit_all(df, events)
    print(f"  fitted {fits.height:,} (event × sensor) tails")

    fits.write_csv(FIT_CSV)
    print(f"  wrote {FIT_CSV.relative_to(ROOT)}")

    print_summary(fits)

    plot_distributions(fits, DIST_PNG)
    print(f"  wrote {DIST_PNG.relative_to(ROOT)}")

    plot_examples(examples, EXAMPLES_PNG)
    print(f"  wrote {EXAMPLES_PNG.relative_to(ROOT)}")

    plot_representative_events(df, events, fits, REPRESENTATIVE_PNG)
    print(f"  wrote {REPRESENTATIVE_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
