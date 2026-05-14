"""Sensor-location loader.

Reads ``data/SMS_locations.csv``, which holds three independent (X, Y, Z)
measurements per sensor pair plus the means and standard deviations. The
file has duplicated ``X,Y,Z`` column names in its header, so we read it
row-wise and reshape rather than relying on polars header parsing.

The "pairs" in the source CSV are physical co-locations: the 10 cm and
40 cm TEROS-12 sensors at each station share a single (X, Y) on the
surface, only differing in installation depth. SMS 10 has no 10 cm
partner; SMS 3,4,5 has three sensors at one location (SMS 3 is reported
above ground at -10 cm in metadata).

Z sign convention
-----------------
SMS_locations.csv Z is already in the same frame as the DEM
(``data/DEM/Mesh_swale_site.vtk``). For 5 of the 8 sensor pairs the
raw CSV Z matches the local DEM surface elevation to within ~5 cm.
Three outliers (SMS 1,2; SMS 3,4,5; SMS 11,12) sit ~0.33-0.42 m
below the DEM surface — close to the 40 cm sensor depth, suggesting
the surveyor recorded the buried-sensor elevation rather than the
surface marker for those rows. The loader returns Z as-is.

The Widmer location names ("Top slope", "Bottom slope", ...) refer
to the *top/bottom of the swale construction* (upstream/downstream
end of the dug feature), not the topographic top of the hillslope.
The DEM shows the swale sits in the *lower* part of the local
terrain; the higher ground is east, where the control plot lies.

DEM frame alignment
-------------------
The SMS_locations frame and the DEM frame share the same X/Y origin
and orientation (the swale ends up at the same position in both).
The earlier-seen mismatch between the SMS X range (~-7 to +6) and a
naive read of the DEM .txt file was an artifact of reading the wrong
column ordering; the .vtk file confirms alignment.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SensorPair:
    """One station: the (X, Y, Z) coordinate shared by 10 cm + 40 cm sensors."""

    label: str                 # the CSV's ``type`` cell, e.g. "'SMS 1,2'"
    sensor_ids: tuple[str, ...]  # canonical SMS IDs, e.g. ("SMS01", "SMS02")
    x: float
    y: float
    z: float
    x_std: float
    y_std: float
    z_std: float
    treatment: str | None      # "swale" | "control" | None for landmarks
    widmer_location: str | None  # e.g. "Top slope", "Mound", "Step"


_WIDMER_LOCATION_BY_PAIR: dict[tuple[str, ...], tuple[str, str]] = {
    # (canonical sensor_ids) -> (treatment, widmer_location)
    ("SMS01", "SMS02"):                ("swale",   "Top slope"),
    ("SMS03", "SMS04", "SMS05"):       ("swale",   "Mound"),
    ("SMS06", "SMS07"):                ("swale",   "Bottom slope 1"),
    ("SMS08", "SMS09"):                ("swale",   "Bottom slope 2"),
    ("SMS10",):                        ("swale",   "Step"),
    ("SMS11", "SMS12"):                ("control", "Top slope"),
    ("SMS13", "SMS14"):                ("control", "Mid slope"),
    ("SMS15", "SMS16"):                ("control", "Bottom slope"),
}


_QUOTE_CHARS = "'\"‘’“”"  # straight + smart quotes


def _parse_sensor_ids(label: str) -> tuple[str, ...]:
    """Turn a label like ``"'SMS 1, 2'"`` into ``("SMS01", "SMS02")``.

    The CSV labels are inconsistent in their quoting: some use straight
    single quotes ``'``, some use smart curly quotes ``'``, some are
    double-quoted on the outside with single quotes inside. Strip all
    of them.

    Returns an empty tuple for non-SMS labels (weather station, soil
    profile markers).
    """
    raw = label.strip().strip(_QUOTE_CHARS)
    if not raw.upper().startswith("SMS"):
        return ()
    tail = raw[3:].strip()
    out: list[str] = []
    for part in tail.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(f"SMS{int(part):02d}")
        except ValueError:
            continue
    return tuple(out)


def load_sensor_pairs(csv_path: Path) -> list[SensorPair]:
    """Load all sensor pairs (and landmarks) from ``SMS_locations.csv``.

    The CSV has duplicated ``X,Y,Z`` headers, so we read rows positionally
    and pick the ``X_av, Y_av, Z_av`` columns (positions 10, 12, 14) plus
    the matching std columns (11, 13, 15).

    Args:
        csv_path: Path to ``data/SMS_locations.csv``.

    Returns:
        A list of ``SensorPair``, one per non-empty row, in source order.
        Landmark rows (weather station, soil profiles) come back with
        ``sensor_ids = ()`` and ``treatment = widmer_location = None``.
    """
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    pairs: list[SensorPair] = []
    with csv_path.open() as f:
        # The CSV's first column wraps labels with embedded commas in
        # standard double quotes ("'SMS 1, 2'"). Default csv.reader
        # handles those correctly; we then strip inner quotes when
        # parsing the sensor IDs.
        reader = csv.reader(f)
        next(reader, None)  # skip the duplicated header
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                x = float(row[10]); x_std = float(row[11])
                y = float(row[12]); y_std = float(row[13])
                z = float(row[14]); z_std = float(row[15])
            except (IndexError, ValueError):
                continue

            sensor_ids = _parse_sensor_ids(row[0])
            treatment_loc = _WIDMER_LOCATION_BY_PAIR.get(sensor_ids, (None, None))
            pairs.append(SensorPair(
                label=row[0].strip().strip(_QUOTE_CHARS),
                sensor_ids=sensor_ids,
                x=x, y=y, z=z,
                x_std=x_std, y_std=y_std, z_std=z_std,
                treatment=treatment_loc[0],
                widmer_location=treatment_loc[1],
            ))
    return pairs


def sensor_pairs(csv_path: Path) -> list[SensorPair]:
    """Pairs filtered to just SMS sensors (drops the landmark rows)."""
    return [p for p in load_sensor_pairs(csv_path) if p.sensor_ids]


def sensor_id_to_coords(
    pairs: Iterable[SensorPair],
) -> dict[str, tuple[float, float, float]]:
    """``{sensor_id: (x, y, z)}`` lookup. All sensors in a pair share the same (x, y, z)."""
    out: dict[str, tuple[float, float, float]] = {}
    for p in pairs:
        for sid in p.sensor_ids:
            out[sid] = (p.x, p.y, p.z)
    return out
