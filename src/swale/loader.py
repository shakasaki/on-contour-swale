"""Top-level loader for the swale soil-sensor dataset.

Discovers every per-logger CSV and Excel snapshot under ``data_root``, runs the
appropriate reader, joins in the metadata, deduplicates overlapping records
across sources (CSV preferred), reindexes onto a regular time grid per
(logger, sensor, variable), and optionally caches the result as Parquet.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Literal

import polars as pl

from swale.metadata import parse_metadata
from swale.readers import read_logger_csv, read_logger_parquet, read_logger_xlsx
from swale.schema import (
    LOGGER_INFO,
    NON_FOREST_LOGGERS,
    logger_serial_from_name,
)

# Numerical tolerance for treating two source values as agreeing. Combined
# absolute + relative ("isclose"-style): a key is a conflict only when
# |x - y| > _ABS_TOL + _REL_TOL * max(|x|, |y|). Loose enough to swallow
# the CSV's display-rounding (typically 3 decimals on the m³/m³ values),
# tight enough to catch the genuine 'Saturation Extract EC' vs 'Bulk EC'
# semantic mismatch.
_ABS_TOL = 1e-3
_REL_TOL = 1e-3

# Source-format priority: lower wins on dedup. XLSX snapshots carry the
# full-precision calibrated values, so they win outright. The ZENTRA Cloud
# v5 API also returns full precision and stays current, so it is preferred
# over the display-rounded CSV exports in the overlap window; CSV only fills
# history that predates each logger's v5 record.
_SOURCE_PRIORITY: dict[str, int] = {"xlsx": 0, "zentracloud": 1, "csv": 2}

# Plausibility window for timestamps. Anything outside this range is
# treated as a logger clock glitch (e.g. battery-failure date resets) and
# dropped with a warning.
_MIN_PLAUSIBLE_YEAR = 2018
_MAX_PLAUSIBLE_YEAR = 2030


def _discover_files(
    data_root: Path,
    zentracloud_dir: Path | None,
) -> tuple[list[tuple[str, Path]],
           list[tuple[str, Path]],
           list[tuple[str, Path]]]:
    """Return (csv_jobs, xlsx_jobs, parquet_jobs); each entry is (serial, path)."""
    csv_jobs: list[tuple[str, Path]] = []
    xlsx_jobs: list[tuple[str, Path]] = []
    parquet_jobs: list[tuple[str, Path]] = []

    for logger_serial in NON_FOREST_LOGGERS:
        logger_dir = data_root / logger_serial
        if not logger_dir.is_dir():
            continue
        for csv_path in sorted(logger_dir.glob("*.csv")):
            # Skip raw-counts files; only processed values are loaded.
            if "Raw" in csv_path.name and "Configuration" in csv_path.name:
                continue
            csv_jobs.append((logger_serial, csv_path))

    xlsx_dir = data_root / "data_xlsx"
    if xlsx_dir.is_dir():
        for xlsx_path in sorted(xlsx_dir.glob("*.xlsx")):
            serial = logger_serial_from_name(xlsx_path.name)
            if serial in NON_FOREST_LOGGERS:
                xlsx_jobs.append((serial, xlsx_path))

    # ZENTRA Cloud v5 dumps: one <serial>.parquet per logger, written by
    # scripts/fetch_zentracloud.py.
    if zentracloud_dir is not None and Path(zentracloud_dir).is_dir():
        for serial in NON_FOREST_LOGGERS:
            pq = Path(zentracloud_dir) / f"{serial}.parquet"
            if pq.is_file():
                parquet_jobs.append((serial, pq))

    return csv_jobs, xlsx_jobs, parquet_jobs


def _read_all(
    csv_jobs: list[tuple[str, Path]],
    xlsx_jobs: list[tuple[str, Path]],
    parquet_jobs: list[tuple[str, Path]],
) -> pl.DataFrame:
    """Run readers and stack with a logger_serial column attached."""
    frames: list[pl.DataFrame] = []
    for serial, path in csv_jobs:
        df = read_logger_csv(path)
        if df.height:
            frames.append(df.with_columns(
                pl.lit(serial).alias("logger_serial")
            ))
    for serial, path in xlsx_jobs:
        df = read_logger_xlsx(path)
        if df.height:
            frames.append(df.with_columns(
                pl.lit(serial).alias("logger_serial")
            ))
    for serial, path in parquet_jobs:
        df = read_logger_parquet(path)
        if df.height:
            frames.append(df.with_columns(
                pl.lit(serial).alias("logger_serial")
            ))
    if not frames:
        # Build an empty frame with the right schema rather than returning
        # an empty list; downstream joins assume the columns exist.
        empty = read_logger_csv.__wrapped__ if hasattr(read_logger_csv, "__wrapped__") else None
        return pl.DataFrame()
    return pl.concat(frames, how="vertical_relaxed")


def _detect_conflicts(df: pl.DataFrame, *, on_conflict: str) -> pl.DataFrame:
    """Find (logger, port, variable, timestamp) keys with disagreeing values.

    Returns a small report DataFrame; emits a warning (or raises) per the
    ``on_conflict`` policy. A conflict is declared when ≥2 rows share a key
    and ``|v_max - v_min| > _ABS_TOL + _REL_TOL * max(|v_min|, |v_max|)``.
    Nulls on either side are ignored.

    The combined tolerance is loose enough to absorb the CSV export's
    3-decimal rounding (which would otherwise produce ~600k spurious
    moisture conflicts) but tight enough to flag the genuine 'Saturation
    Extract EC' vs 'Bulk EC' semantic mismatch on the EC channel.
    """
    abs_diff = (pl.col("v_max") - pl.col("v_min")).abs()
    abs_max  = pl.max_horizontal(pl.col("v_max").abs(), pl.col("v_min").abs())
    grouped = (
        df.filter(pl.col("value").is_not_null())
          .group_by(["logger_serial", "port", "variable", "timestamp"])
          .agg([
              pl.col("value").min().alias("v_min"),
              pl.col("value").max().alias("v_max"),
              pl.col("source_format").n_unique().alias("n_sources"),
          ])
          .filter(
              (pl.col("n_sources") > 1)
              & (abs_diff > (_ABS_TOL + _REL_TOL * abs_max))
          )
    )
    if grouped.height:
        per_var = (grouped.group_by("variable")
                          .agg(pl.len().alias("n"))
                          .sort("n", descending=True))
        breakdown = ", ".join(f"{row['variable']}={row['n']}"
                              for row in per_var.iter_rows(named=True))
        msg = (
            f"{grouped.height:,} (logger, port, variable, timestamp) keys "
            f"have disagreeing values across CSV and XLSX sources beyond "
            f"isclose(atol={_ABS_TOL}, rtol={_REL_TOL}). XLSX retained. "
            f"Per-variable counts: {breakdown}."
        )
        if on_conflict == "raise":
            raise ValueError(msg)
        warnings.warn(msg)
    return grouped


def _drop_implausible_timestamps(df: pl.DataFrame) -> pl.DataFrame:
    """Drop rows whose timestamp is outside the plausible deployment window.

    Logger clock glitches occasionally produce timestamps decades into the
    past or future (we observed two 2035-11-29 records in the May-2024
    Excel snapshot for logger 19570). Filter them out and warn once.
    """
    lo = pl.datetime(_MIN_PLAUSIBLE_YEAR, 1, 1)
    hi = pl.datetime(_MAX_PLAUSIBLE_YEAR, 1, 1)
    bad_mask = (pl.col("timestamp") < lo) | (pl.col("timestamp") >= hi)
    n_bad = df.filter(bad_mask).height
    if n_bad:
        warnings.warn(
            f"Dropping {n_bad} rows with implausible timestamps outside "
            f"[{_MIN_PLAUSIBLE_YEAR}, {_MAX_PLAUSIBLE_YEAR}) — likely "
            f"logger clock glitches."
        )
        return df.filter(~bad_mask)
    return df


def _dedup_prefer_xlsx(df: pl.DataFrame) -> pl.DataFrame:
    """Drop duplicate keys, keeping XLSX rows over CSV rows.

    Sort key is (logger_serial, port, variable, timestamp, source_priority)
    so that on tie, the XLSX row sorts first and is kept by ``unique(...,
    keep='first')``. XLSX is preferred because the CSV exports are rounded
    for display (typically 3 decimals on m³/m³ moisture) while the Excel
    snapshots carry the full-precision calibrated values; CSV is only
    retained outside the XLSX coverage window.
    """
    return (
        df.with_columns(
            pl.col("source_format")
              .replace_strict(_SOURCE_PRIORITY, default=99,
                              return_dtype=pl.UInt8)
              .alias("_src_pri")
        )
        .sort(["logger_serial", "port", "variable", "timestamp", "_src_pri"])
        .unique(subset=["logger_serial", "port", "variable", "timestamp"],
                keep="first", maintain_order=True)
        .drop("_src_pri")
    )


def _reindex_group(
    group: pl.DataFrame,
    grid: str | None,
) -> pl.DataFrame:
    """Reindex one (sensor_id, variable) group onto a regular time grid.

    If ``grid`` is None, the cadence is inferred as the mode of consecutive
    timestamp deltas in the group. Missing timestamps become explicit null
    values; metadata columns (sensor_id, location, etc.) are forward-filled
    onto the new rows.
    """
    if group.height < 2:
        return group
    g = group.sort("timestamp")
    if grid is None:
        diffs = g["timestamp"].diff().drop_nulls()
        if diffs.len() == 0:
            return g
        # Mode of inter-sample deltas, in microseconds.
        modal_us_series = diffs.dt.total_microseconds().mode()
        if modal_us_series.len() == 0:
            return g
        modal_us = int(modal_us_series.item(0))
        if modal_us <= 0:
            return g
        cadence = f"{modal_us}us"
    else:
        cadence = grid

    upsampled = g.upsample(time_column="timestamp", every=cadence,
                            maintain_order=True)
    # Forward-fill the metadata columns (sensor_id, port, treatment, etc.).
    # The 'value' column intentionally retains its nulls — those are the
    # gaps the caller asked us to surface — and so does 'error_code': a
    # synthetic grid row is a gap, not a flagged reading.
    fill_cols = [c for c in upsampled.columns
                 if c not in ("timestamp", "value", "error_code")]
    upsampled = upsampled.with_columns([
        pl.col(c).forward_fill().backward_fill() for c in fill_cols
    ])
    return upsampled


def _reindex_all(df: pl.DataFrame, grid: str | None) -> pl.DataFrame:
    pieces: list[pl.DataFrame] = []
    for _, group in df.group_by(["logger_serial", "sensor_id", "variable"],
                                  maintain_order=True):
        pieces.append(_reindex_group(group, grid))
    if not pieces:
        return df
    return pl.concat(pieces, how="vertical_relaxed")


def _enrich_with_metadata(
    df: pl.DataFrame,
    sensors: pl.DataFrame,
    port_mapping: pl.DataFrame,
) -> pl.DataFrame:
    """Add sensor_id, treatment, location, depth_cm, logger_alias, etc."""
    # Map (logger_serial, port) -> sensor_id / sensor_type / aliases.
    df = df.join(
        port_mapping.select(["logger_serial", "port", "sensor_id",
                             "logger_alias", "logger_location"]),
        on=["logger_serial", "port"],
        how="left",
    )
    # Map sensor_id -> location/treatment/depth (non-Forest TEROS only).
    sens_slim = sensors.select([
        "sensor_id", "field_id", "location", "tag", "treatment",
        "depth_cm", "location_notes",
    ])
    df = df.join(sens_slim, on="sensor_id", how="left")
    return df


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load_swale_dataset(
    data_root: Path,
    metadata_xlsx: Path,
    *,
    zentracloud_dir: Path | None | Literal["auto"] = "auto",
    cache_dir: Path | None = None,
    refresh: bool = False,
    grid: str | None | Literal["auto"] = "none",
    on_conflict: Literal["warn", "raise"] = "warn",
) -> pl.DataFrame:
    """Load the consolidated, deduplicated, reindexed swale dataset.

    Args:
        data_root: Folder containing per-logger subdirectories (named after
            the 5-digit serial, e.g. ``05511/``) and a ``data_xlsx/`` folder
            of periodic Excel snapshots.
        metadata_xlsx: Path to the project's Metadata.xlsx with a 'Serials'
            tab.
        zentracloud_dir: Folder holding ``<serial>.parquet`` dumps from
            ``scripts/fetch_zentracloud.py``. ``"auto"`` (default) looks for
            ``<data_root>/../zentracloud``. Pass an explicit path to override,
            or ``None`` to skip the v5 source entirely.
        cache_dir: If given, results are written to (and on subsequent calls
            read from) ``cache_dir / logger=<serial>.parquet``. Set
            ``refresh=True`` to force a rebuild.
        refresh: When True, ignore any existing cache and re-read all files.
        grid: How to handle the time axis.
            - ``"none"`` (default): no reindexing; rows are returned at the
              observed timestamps after dedup.
            - A polars duration string (e.g. ``"15m"``, ``"5m"``): reindex
              every (logger, sensor, variable) onto that fixed cadence.
            - ``"auto"``: infer cadence per (logger, sensor, variable) from
              the mode of consecutive deltas. Be aware that for channels
              whose cadence changed mid-experiment, the modal cadence will
              insert spurious nulls in the slower-cadence segments. Prefer
              an explicit duration when feasible.
        on_conflict: ``"warn"`` (default) emits a UserWarning if the CSV and
            Excel sources disagree on a value. ``"raise"`` raises ValueError
            on the first such disagreement.

    Returns:
        A long-format polars DataFrame with one row per
        (logger, sensor, variable, timestamp). Columns:
        ``timestamp, logger_serial, logger_alias, logger_location, port,
        sensor_id, sensor_type, treatment, location, tag, depth_cm, field_id,
        location_notes, variable, value, error_code, source_format,
        source_file, config_label``. ``error_code`` is the METER quality
        code from the ZENTRA Cloud v5 source (0 = OK, non-zero = flagged);
        it is null for rows that came from CSV or XLSX exports.

    Raises:
        FileNotFoundError: If ``data_root`` or ``metadata_xlsx`` is missing.
        ValueError: With ``on_conflict="raise"`` on any cross-source value
            disagreement beyond ``1e-6``.

    Examples:
        >>> df = load_swale_dataset(
        ...     data_root=Path("/data/swale"),
        ...     metadata_xlsx=Path("/data/swale/Metadata.xlsx"),
        ...     cache_dir=Path("./cache"),
        ... )
        >>> df.filter(pl.col("variable") == "moisture").height > 0
        True

    See Also:
        swale.metadata.parse_metadata: Underlying metadata parser.
        swale.readers.read_logger_csv: Per-file reader for CSV exports.
        swale.readers.read_logger_xlsx: Per-file reader for Excel snapshots.
    """
    data_root = Path(data_root)
    metadata_xlsx = Path(metadata_xlsx)
    if not data_root.is_dir():
        raise FileNotFoundError(data_root)
    if not metadata_xlsx.exists():
        raise FileNotFoundError(metadata_xlsx)

    if zentracloud_dir == "auto":
        zentracloud_dir = data_root.parent / "zentracloud"
    elif zentracloud_dir is not None:
        zentracloud_dir = Path(zentracloud_dir)

    if cache_dir is not None and not refresh:
        cached = _try_load_cache(cache_dir)
        if cached is not None:
            return cached

    sensors, port_mapping = parse_metadata(metadata_xlsx)
    csv_jobs, xlsx_jobs, parquet_jobs = _discover_files(data_root, zentracloud_dir)
    raw = _read_all(csv_jobs, xlsx_jobs, parquet_jobs)
    if raw.height == 0:
        warnings.warn("No data files found under data_root.")
        return raw

    raw = _drop_implausible_timestamps(raw)
    _detect_conflicts(raw, on_conflict=on_conflict)
    deduped = _dedup_prefer_xlsx(raw)
    enriched = _enrich_with_metadata(deduped, sensors, port_mapping)
    if grid == "none" or grid is None:
        reindexed = enriched.sort(["logger_serial", "sensor_id", "variable",
                                    "timestamp"])
    else:
        cadence = None if grid == "auto" else grid
        reindexed = _reindex_all(enriched, grid=cadence)

    # Final column order — stable for downstream consumers.
    column_order = [
        "timestamp", "logger_serial", "logger_alias", "logger_location",
        "port", "sensor_id", "sensor_type",
        "treatment", "location", "tag", "depth_cm",
        "field_id", "location_notes",
        "variable", "value", "error_code",
        "source_format", "source_file", "config_label",
    ]
    reindexed = reindexed.select([c for c in column_order
                                   if c in reindexed.columns])

    if cache_dir is not None:
        _write_cache(reindexed, cache_dir)

    return reindexed


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _cache_partition(cache_dir: Path, logger_serial: str) -> Path:
    return cache_dir / f"logger={logger_serial}.parquet"


def _try_load_cache(cache_dir: Path) -> pl.DataFrame | None:
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return None
    parts = sorted(cache_dir.glob("logger=*.parquet"))
    if not parts:
        return None
    return pl.concat([pl.read_parquet(p) for p in parts], how="vertical_relaxed")


def _write_cache(df: pl.DataFrame, cache_dir: Path) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for serial in NON_FOREST_LOGGERS:
        part = df.filter(pl.col("logger_serial") == serial)
        if part.height == 0:
            continue
        part.write_parquet(_cache_partition(cache_dir, serial))
