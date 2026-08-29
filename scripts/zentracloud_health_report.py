"""Sensor-health report from the raw ZENTRA Cloud v5 parquet dumps.

Reads ``data/zentracloud/{05511,19570,19574}.parquet`` (written by
``fetch_zentracloud.py``), joins each ``port_num`` to the physical sensor via
``Metadata.xlsx``, and classifies every port by its ``error_code`` history
(non-zero = METER codes 136 "value outside expected range" / 137 "invalid
value" etc.).

Output: a Markdown field report at ``notes/field_sensor_faults.md`` naming
exactly which datalogger + sensor is failing and since when.

Usage::

    conda run -n swale python scripts/zentracloud_health_report.py
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from swale.display_names import display
from swale.metadata import parse_metadata

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
ZC_DIR = ROOT / "data" / "zentracloud"
META_XLSX = ROOT / "data" / "Metadata.xlsx"
OUT_MD = ROOT / "notes" / "field_sensor_faults.md"

# logger serial -> parquet basename
LOGGERS = {
    "05511": "z6-05511  (control slope)",
    "19570": "z6-19570  (top of swale)",
    "19574": "z6-19574  (bottom of swale)",
}

# daily error-fraction thresholds for classification
DEAD_FRAC = 0.95        # >= this over the whole record  -> dead
HEALTHY_FRAC = 0.02     # <  this over the whole record  -> healthy
ONSET_FRAC = 0.20       # first day above this           -> fault onset
RECENT_DAYS = 14        # window used to decide "still failing"


def load_readings() -> pl.DataFrame:
    frames = []
    for serial in LOGGERS:
        p = ZC_DIR / f"{serial}.parquet"
        df = pl.read_parquet(p, columns=["datetime", "port_num", "error_code"])
        frames.append(df.with_columns(logger_serial=pl.lit(serial)))
    return pl.concat(frames)


def daily_error_fraction(df: pl.DataFrame) -> pl.DataFrame:
    """One row per (logger_serial, port_num, day) with the flagged fraction."""
    return (
        df.with_columns(
            day=pl.col("datetime").dt.date(),
            bad=(pl.col("error_code") != 0),
        )
        .group_by("logger_serial", "port_num", "day")
        .agg(
            n=pl.len(),
            n_bad=pl.col("bad").sum(),
        )
        .with_columns(frac=pl.col("n_bad") / pl.col("n"))
        .sort("logger_serial", "port_num", "day")
    )


def summarise_port(sub: pl.DataFrame) -> dict:
    """Classify one port's whole history. `sub` is its daily rows, sorted."""
    total_n = int(sub["n"].sum())
    total_bad = int(sub["n_bad"].sum())
    overall = total_bad / total_n if total_n else 0.0

    last_day = sub["day"].max()
    recent = sub.filter(pl.col("day") >= last_day - pl.duration(days=RECENT_DAYS))
    recent_frac = (
        recent["n_bad"].sum() / recent["n"].sum() if recent["n"].sum() else 0.0
    )

    # A "bad day" needs a meaningful sample so a sparse partial first/last
    # day with one flagged reading can't masquerade as an onset.
    bad_days = sub.filter((pl.col("frac") >= ONSET_FRAC) & (pl.col("n") >= 100))
    onset = bad_days["day"].min() if bad_days.height else None
    # last clean day before onset
    last_ok = None
    if onset is not None:
        before = sub.filter((pl.col("day") < onset) & (pl.col("frac") < HEALTHY_FRAC))
        last_ok = before["day"].max() if before.height else None
    recovered = bad_days["day"].max() if bad_days.height else None
    # A single bad day (e.g. a deployment-day settling blip) is not a fault.
    sustained = bad_days.height >= 3

    if recent_frac >= DEAD_FRAC:
        status = "DEAD"                       # currently returning nothing usable
    elif recent_frac >= ONSET_FRAC:
        status = "DEGRADING"
    elif not sustained:
        status = "healthy"
    elif recent_frac < HEALTHY_FRAC:
        status = "recovered"
    else:
        status = "INTERMITTENT"

    return {
        "status": status,
        "overall_frac": overall,
        "recent_frac": recent_frac,
        "onset": onset,
        "last_ok": last_ok,
        "recovered_by": recovered,
        "n_bad": total_bad,
        "n_total": total_n,
    }


def build_report() -> str:
    readings = load_readings()
    span_lo, span_hi = readings["datetime"].min(), readings["datetime"].max()
    daily = daily_error_fraction(readings)

    sensors, port_mapping = parse_metadata(META_XLSX)
    pm = port_mapping.select(
        "logger_serial", "port", "sensor_id", "sensor_type", "logger_location"
    )
    depth = dict(zip(sensors["sensor_id"], sensors["depth_cm"]))
    tag = dict(zip(sensors["sensor_id"], sensors["tag"]))

    rows = []
    for (serial, port), sub in daily.group_by(
        ["logger_serial", "port_num"], maintain_order=True
    ):
        info = summarise_port(sub.sort("day"))
        match = pm.filter(
            (pl.col("logger_serial") == serial) & (pl.col("port") == port)
        )
        if match.height:
            m = match.row(0, named=True)
            sensor_id = m["sensor_id"]
            stype = m["sensor_type"]
            loc = m["logger_location"]
        else:
            sensor_id, stype, loc = f"port{port}", "?", "?"
        rows.append({
            "serial": serial,
            "port": port,
            "sensor_id": sensor_id,
            "display": display(sensor_id) if stype == "TEROS12" else "-",
            "sensor_type": stype,
            "depth_cm": depth.get(sensor_id),
            "position": tag.get(sensor_id),
            "location": loc,
            **info,
        })

    tbl = pl.DataFrame(rows).sort(
        ["serial", "port"]
    )

    faults = tbl.filter(pl.col("status").is_in(["DEAD", "DEGRADING", "INTERMITTENT"]))
    recovered = tbl.filter(pl.col("status") == "recovered")

    def fmt_row(r: dict) -> str:
        # Onset / last-OK only mean something for a sensor with a real fault.
        show_dates = r["status"] != "healthy"
        onset = (r["onset"] or "—") if show_dates else "—"
        last_ok = (r["last_ok"] or "—") if show_dates else "—"
        return (
            f"| {r['serial']} | Port {r['port']} | {r['sensor_id']} "
            f"| {r['display']} | {r['sensor_type']} "
            f"| {r['depth_cm'] if r['depth_cm'] is not None else '—'} "
            f"| {r['status']} | {100*r['overall_frac']:.1f}% | {100*r['recent_frac']:.1f}% "
            f"| {last_ok} | {onset} |"
        )

    lines: list[str] = []
    lines.append("# Field sensor faults — ZENTRA Cloud v5 data")
    lines.append("")
    lines.append(
        f"Generated by `scripts/zentracloud_health_report.py` from "
        f"`data/zentracloud/*.parquet`."
    )
    lines.append("")
    lines.append(f"- Data span: **{span_lo:%Y-%m-%d %H:%M} → {span_hi:%Y-%m-%d %H:%M} UTC**")
    lines.append(
        f"- A reading is \"flagged\" when METER `error_code` is non-zero "
        f"(136 = value outside expected range, 137 = invalid value)."
    )
    lines.append(
        f"- Onset = first calendar day with ≥{100*ONSET_FRAC:.0f}% of that "
        f"sensor's readings flagged; last-OK = last prior day under "
        f"{100*HEALTHY_FRAC:.0f}%."
    )
    lines.append("")

    lines.append("## Currently failing")
    lines.append("")
    if faults.height:
        lines.append(
            "| Logger | Port | Sensor | Display | Type | Depth cm | Status "
            "| Flagged (all) | Flagged (last 14 d) | Last OK | Since |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in faults.iter_rows(named=True):
            lines.append(fmt_row(r))
    else:
        lines.append("_None._")
    lines.append("")

    if recovered.height:
        lines.append("## Recovered (had a fault window, now clean)")
        lines.append("")
        lines.append(
            "| Logger | Port | Sensor | Display | Type | Depth cm | Status "
            "| Flagged (all) | Flagged (last 14 d) | Last OK | Since |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in recovered.iter_rows(named=True):
            rr = dict(r)
            lines.append(fmt_row(rr) + f"  <!-- recovered by {r['recovered_by']} -->")
        lines.append("")

    lines.append("## All ports")
    lines.append("")
    lines.append(
        "| Logger | Port | Sensor | Display | Type | Depth cm | Status "
        "| Flagged (all) | Flagged (last 14 d) | Last OK | Since |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in tbl.iter_rows(named=True):
        lines.append(fmt_row(r))
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    md = build_report()
    OUT_MD.write_text(md)
    print(md)
    print(f"\nwritten -> {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
