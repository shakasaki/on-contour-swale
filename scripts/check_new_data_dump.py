"""Unpack the latest METER ZL6 portal CSV dump and diff against the cache.

Usage::

    PYTHONPATH=src python3 scripts/check_new_data_dump.py

What it does
------------
1. Unzips every ``data/All-z6-*.zip`` into ``data/unpacked/<logger_serial>/``.
2. Reads each processed-data CSV through ``swale.readers.read_logger_csv``.
3. Loads the cached parquet (the current DB state, hybrid XLSX+CSV).
4. Reports, per logger and per variable:
     - coverage: time range of new dump vs cache
     - row counts (new dump vs cache, on the shared time window)
     - value disagreement count and the largest deltas
6. Writes ``plots/check_new_data_dump.csv`` with the per-(sensor, variable)
   summary so you can browse anomalies.

This is a one-off diagnostic — it does *not* mutate the cache.

Tunables at the top of the script.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import polars as pl

from swale.config import load_settings
from swale.metadata import parse_metadata
from swale.readers import read_logger_csv

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UNPACK_DIR = DATA_DIR / "unpacked"
CACHE_DIR = ROOT / "cache"
REPORT_CSV = ROOT / "plots" / "check_new_data_dump.csv"

# Tolerance for declaring "same value across sources" — same as the loader's
# (abs + rel max). Catches semantic-mismatch jumps without flagging CSV
# 3-decimal display rounding.
ABS_TOL = 1e-3
REL_TOL = 1e-3

# Filename pattern: "All-z6-XXXXX - <alias>(z6-XXXXX)-<timestamp>.zip"
ZIP_LOGGER_RE = re.compile(r"All-z6-(\d{5})")

# Skip raw-counts files; the loader does the same.
RAW_CSV_PREFIX_RE = re.compile(r"-Raw-Configuration", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Unpack
# ---------------------------------------------------------------------------

def unpack_zips(data_dir: Path, unpack_dir: Path) -> dict[str, list[Path]]:
    """Unzip every All-z6-*.zip into unpack_dir/<logger_serial>/.

    Returns a dict ``{logger_serial: [unpacked_csv_paths]}``, skipping
    Raw-Configuration files.
    """
    zips = sorted(data_dir.glob("All-z6-*.zip"))
    if not zips:
        print("  no zip files found in", data_dir)
        return {}

    out: dict[str, list[Path]] = {}
    for z in zips:
        m = ZIP_LOGGER_RE.search(z.name)
        if not m:
            print(f"  skip (no logger serial in name): {z.name}")
            continue
        serial = m.group(1)
        dest = unpack_dir / serial
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(z, "r") as zf:
            zf.extractall(dest)

        csvs = [p for p in sorted(dest.glob("*.csv"))
                if not RAW_CSV_PREFIX_RE.search(p.name)]
        out[serial] = csvs
        print(f"  {z.name} -> {len(csvs)} processed CSVs in {dest.relative_to(ROOT)}")
    return out


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def read_dump_frames(csvs_by_logger: dict[str, list[Path]]) -> pl.DataFrame:
    """Run read_logger_csv over every unpacked CSV, tag with logger_serial."""
    frames: list[pl.DataFrame] = []
    for serial, csvs in csvs_by_logger.items():
        for csv_path in csvs:
            df = read_logger_csv(csv_path)
            if df.height == 0:
                continue
            df = df.with_columns(pl.lit(serial).alias("logger_serial"))
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="vertical_relaxed")


def load_cache(cache_dir: Path) -> pl.DataFrame:
    parts = sorted(cache_dir.glob("logger=*.parquet"))
    return pl.concat([pl.read_parquet(p) for p in parts], how="vertical_relaxed")


def coverage_summary(dump: pl.DataFrame, cache: pl.DataFrame) -> pl.DataFrame:
    """Time range of dump vs cache per logger."""
    def _per_logger(df: pl.DataFrame, suffix: str) -> pl.DataFrame:
        return (df.group_by("logger_serial")
                  .agg([
                      pl.col("timestamp").min().alias(f"min_{suffix}"),
                      pl.col("timestamp").max().alias(f"max_{suffix}"),
                      pl.len().alias(f"rows_{suffix}"),
                  ]))
    a = _per_logger(dump,  "dump")
    b = _per_logger(cache, "cache")
    return a.join(b, on="logger_serial", how="full", coalesce=True).sort("logger_serial")


def disagreement_report(
    dump: pl.DataFrame,
    cache: pl.DataFrame,
    sensors: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per-(sensor, variable) row counts, overlap counts, disagreement counts.

    Joins dump and cache on (logger_serial, port, variable, timestamp).
    A "disagreement" is a key present in both where
        |v_dump - v_cache| > ABS_TOL + REL_TOL * max(|v_dump|, |v_cache|)
    Returns (per_sensor_var_summary, worst_offenders).
    """
    # Attach sensor_id via the port_mapping side of the metadata. The cache
    # already has sensor_id; the dump only has port.
    # Easiest: derive (logger, port) -> sensor_id from cache itself.
    port2sid = (cache.select(["logger_serial", "port", "sensor_id"])
                       .unique()
                       .filter(pl.col("sensor_id").is_not_null()))
    dump_s = dump.join(port2sid, on=["logger_serial", "port"], how="left")

    # Restrict both sides to TEROS12 + ATMOS14 + ECRN100 (the physical channels
    # we care about; battery/baro precision is low and noisy at the edges).
    keep = ["TEROS12", "ATMOS14", "ECRN100"]
    dump_s = dump_s.filter(pl.col("sensor_type").is_in(keep))
    cache_s = cache.filter(pl.col("sensor_type").is_in(keep))

    key = ["logger_serial", "port", "variable", "timestamp"]
    merged = (
        dump_s.select(key + ["sensor_id", "value"])
              .rename({"value": "v_dump"})
              .join(
                  cache_s.select(key + ["value"]).rename({"value": "v_cache"}),
                  on=key,
                  how="full",
                  coalesce=True,
              )
    )

    abs_diff = (pl.col("v_dump") - pl.col("v_cache")).abs()
    abs_max = pl.max_horizontal(pl.col("v_dump").abs(), pl.col("v_cache").abs())
    disagree = (
        pl.col("v_dump").is_not_null()
        & pl.col("v_cache").is_not_null()
        & (abs_diff > (ABS_TOL + REL_TOL * abs_max))
    )

    summary = (
        merged.with_columns([
            disagree.alias("is_disagree"),
            (pl.col("v_dump").is_not_null() & pl.col("v_cache").is_null()).alias("only_dump"),
            (pl.col("v_dump").is_null() & pl.col("v_cache").is_not_null()).alias("only_cache"),
            (pl.col("v_dump").is_not_null() & pl.col("v_cache").is_not_null()).alias("both"),
            abs_diff.alias("abs_diff"),
        ])
        .group_by(["logger_serial", "sensor_id", "variable"])
        .agg([
            pl.col("both").sum().alias("n_both"),
            pl.col("only_dump").sum().alias("n_only_dump"),
            pl.col("only_cache").sum().alias("n_only_cache"),
            pl.col("is_disagree").sum().alias("n_disagree"),
            pl.col("abs_diff").max().alias("max_abs_diff"),
            pl.col("abs_diff")
              .filter(pl.col("is_disagree"))
              .median()
              .alias("median_disagree_diff"),
        ])
        .sort(["logger_serial", "sensor_id", "variable"])
    )

    worst = (
        merged.filter(disagree)
              .with_columns(abs_diff.alias("abs_diff"))
              .sort("abs_diff", descending=True)
              .head(20)
              .select(["timestamp", "logger_serial", "sensor_id", "variable",
                       "v_cache", "v_dump", "abs_diff"])
    )

    return summary, worst


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    settings = load_settings()
    print("Unpacking zips...")
    csvs_by_logger = unpack_zips(DATA_DIR, UNPACK_DIR)
    if not csvs_by_logger:
        return

    print("\nReading dump CSVs...")
    dump = read_dump_frames(csvs_by_logger)
    print(f"  dump rows: {dump.height:,}")
    print(f"  dump time range: {dump['timestamp'].min()} -> {dump['timestamp'].max()}")

    print("\nLoading cache...")
    cache = load_cache(CACHE_DIR)
    print(f"  cache rows: {cache.height:,}")
    print(f"  cache time range: {cache['timestamp'].min()} -> {cache['timestamp'].max()}")

    print("\nCoverage (per logger):")
    cov = coverage_summary(dump, cache)
    print(cov)

    print("\nLoading metadata for sensor_id map...")
    sensors, _ = parse_metadata(settings.metadata_xlsx)

    print("\nComputing per-(sensor, variable) summary and worst-offender list...")
    summary, worst = disagreement_report(dump, cache, sensors)
    REPORT_CSV.parent.mkdir(exist_ok=True)
    summary.write_csv(REPORT_CSV)
    print(f"  per-(sensor, variable) summary -> {REPORT_CSV.relative_to(ROOT)}")

    print("\n--- Per-sensor summary ---")
    with pl.Config(tbl_rows=50, tbl_cols=20):
        print(summary)

    print("\n--- Worst 20 disagreements ---")
    with pl.Config(tbl_rows=20, tbl_cols=20):
        print(worst)

    # Headline numbers
    total_both = int(summary["n_both"].sum())
    total_disagree = int(summary["n_disagree"].sum())
    total_only_dump = int(summary["n_only_dump"].sum())
    total_only_cache = int(summary["n_only_cache"].sum())
    print("\n--- Headline ---")
    print(f"  overlapping keys (in both):       {total_both:,}")
    print(f"  disagreements beyond tolerance:   {total_disagree:,}  "
          f"({100.0 * total_disagree / max(1, total_both):.3f}%)")
    print(f"  rows present only in new dump:    {total_only_dump:,}")
    print(f"  rows present only in cache:       {total_only_cache:,}")


if __name__ == "__main__":
    main()
