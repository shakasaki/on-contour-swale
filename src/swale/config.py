"""Project configuration loaded from JSON.

Single entry point: ``load_settings()`` reads ``config/settings.json`` from
the repo root and returns a typed-ish dict. Analyses call
``apply_equilibration_cutoff(df, settings)`` near the top of their pipeline
to drop the per-sensor settling window before any aggregation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETTINGS_PATH = _REPO_ROOT / "config" / "settings.json"


@dataclass(frozen=True)
class Equilibration:
    days_default: int
    days_overrides: dict[str, int]
    variables: tuple[str, ...]

    def days_for(self, sensor_id: str) -> int:
        return int(self.days_overrides.get(sensor_id, self.days_default))


@dataclass(frozen=True)
class SpatialFrame:
    """Sign multipliers that map raw (X, Y) to the canonical frame.

    Canonical convention: +X = East, +Y = North, +Z = up. Multiply raw
    x and y by these signs at load time so every downstream consumer
    (loaders, helpers, plots) sees data already in the canonical frame.
    """

    raw_x_sign: int
    raw_y_sign: int


@dataclass(frozen=True)
class Settings:
    equilibration: Equilibration
    data_root: Path
    metadata_xlsx: Path
    rain_gauge_valid_until: str
    treatment_colors: dict[str, str]
    spatial_frame: SpatialFrame
    raw: dict[str, Any]


def load_settings(path: Path | None = None) -> Settings:
    """Load and validate ``config/settings.json``.

    Args:
        path: Override path. Defaults to ``<repo>/config/settings.json``.

    Returns:
        A frozen ``Settings`` dataclass.
    """
    p = Path(path) if path is not None else _DEFAULT_SETTINGS_PATH
    raw = json.loads(p.read_text())

    eq = raw["equilibration"]
    equilibration = Equilibration(
        days_default=int(eq["days_default"]),
        days_overrides={str(k): int(v) for k, v in eq.get("days_overrides", {}).items()},
        variables=tuple(eq.get("variables", ["moisture", "soil_temp", "sat_extract_ec"])),
    )
    data = raw["data"]
    sf = raw.get("spatial_frame", {"raw_x_sign": 1, "raw_y_sign": 1})

    # Resolve data_root and metadata_xlsx relative to the repo root if they
    # aren't absolute — so the project survives directory renames and runs
    # against the in-repo data/ tree without a config edit.
    metadata_path = Path(data["metadata_xlsx"])
    if not metadata_path.is_absolute():
        metadata_path = _REPO_ROOT / metadata_path

    data_root = Path(data["data_root"])
    if not data_root.is_absolute():
        data_root = _REPO_ROOT / data_root

    return Settings(
        equilibration=equilibration,
        data_root=data_root,
        metadata_xlsx=metadata_path,
        rain_gauge_valid_until=str(data["rain_gauge_valid_until"]),
        treatment_colors=dict(raw.get("treatment_colors", {})),
        spatial_frame=SpatialFrame(
            raw_x_sign=int(sf["raw_x_sign"]),
            raw_y_sign=int(sf["raw_y_sign"]),
        ),
        raw=raw,
    )


def per_sensor_first_valid(df: pl.DataFrame) -> pl.DataFrame:
    """For each sensor_id, the timestamp of its first non-null reading.

    Used as the anchor for the equilibration cutoff (days counted from
    the first time the sensor reported a real value, not from the logger
    powering on).
    """
    return (
        df.filter(pl.col("value").is_not_null())
          .group_by("sensor_id")
          .agg(pl.col("timestamp").min().alias("first_valid"))
    )


def apply_equilibration_cutoff(
    df: pl.DataFrame,
    settings: Settings,
    *,
    variables: tuple[str, ...] | None = None,
) -> pl.DataFrame:
    """Drop rows within the equilibration window for the affected variables.

    For each sensor_id, computes ``cutoff = first_valid + days_for(sensor_id)``
    and drops rows with ``timestamp < cutoff`` for the configured variables.
    Rows for variables outside the equilibration set (e.g. precipitation,
    battery) pass through unchanged.

    Args:
        df: Long-format swale dataframe from ``load_swale_dataset``.
        settings: Loaded ``Settings``.
        variables: Optional override of which variables to cut. Defaults to
            ``settings.equilibration.variables``.

    Returns:
        A new dataframe with equilibration-window rows removed.
    """
    target_vars = tuple(variables) if variables is not None else settings.equilibration.variables
    if not target_vars:
        return df

    fv = per_sensor_first_valid(df)

    overrides = settings.equilibration.days_overrides
    default_days = settings.equilibration.days_default
    if overrides:
        days_expr = (
            pl.col("sensor_id")
              .replace_strict(
                  {k: int(v) for k, v in overrides.items()},
                  default=default_days,
                  return_dtype=pl.Int32,
              )
        )
    else:
        days_expr = pl.lit(default_days, dtype=pl.Int32)

    fv = fv.with_columns([
        days_expr.alias("eq_days"),
        (pl.col("first_valid") + pl.duration(days=days_expr)).alias("eq_cutoff"),
    ])

    out = df.join(fv.select(["sensor_id", "eq_cutoff"]), on="sensor_id", how="left")

    in_eq_window = (
        pl.col("variable").is_in(list(target_vars))
        & pl.col("eq_cutoff").is_not_null()
        & (pl.col("timestamp") < pl.col("eq_cutoff"))
    )
    return out.filter(~in_eq_window).drop("eq_cutoff")
