"""Schema constants and string-normalization tables for the swale loader.

Single source of truth for the textual quirks of the METER/Decagon ZL6 data
exports (CSV and Excel). Both formats describe each data column with three
header rows: row 1 is the port label, row 2 is the sensor type, row 3 is the
unit + measurement name. The strings differ between formats (ASCII vs Unicode)
and across firmware/software versions; the maps below normalize them.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Loggers we ingest. Forest logger 05533 is excluded by user decision.
# ---------------------------------------------------------------------------

NON_FOREST_LOGGERS: tuple[str, ...] = ("05511", "19570", "19574")
FOREST_LOGGER: str = "05533"

# Logger metadata derived from the "Dataloggers" subtable in Metadata.xlsx.
LOGGER_INFO: dict[str, dict[str, str]] = {
    "05511": {"alias": "Log3", "location": "Control slope"},
    "19570": {"alias": "Log2", "location": "Top of Swale"},
    "19574": {"alias": "Log1", "location": "Bottom of Swale"},
}

# ---------------------------------------------------------------------------
# Sensor type normalization. Excel uses "TEROS 12"; CSV uses
# "TEROS 12 Moisture/Temp/EC". Same physical sensor, different label.
# ---------------------------------------------------------------------------

SENSOR_TYPE_MAP: dict[str, str] = {
    "teros 12": "TEROS12",
    "teros 12 moisture/temp/ec": "TEROS12",
    "atmos 14": "ATMOS14",
    "atmos 14 humidity/temp/barometer": "ATMOS14",
    "ecrn-100": "ECRN100",
    "ecrn-100 precipitation": "ECRN100",
    "battery": "BATTERY",
    "barometer": "BAROMETER",
    "unrecognized": "UNRECOGNIZED",
    "unrecognized sensor": "UNRECOGNIZED",
}

# Sensor types we want to keep in the output. UNRECOGNIZED rows are dropped:
# they appear during the brief windows when a logger reconfiguration has not
# yet identified a newly attached probe, and the values are raw counts of
# unknown provenance.
KEPT_SENSOR_TYPES: frozenset[str] = frozenset(
    {"TEROS12", "ATMOS14", "ECRN100", "BATTERY", "BAROMETER"}
)

# ---------------------------------------------------------------------------
# Variable normalization. The third header row carries strings like
# " m3/m3 Water Content" (CSV, leading space) or "m³/m³ Water Content" (Excel).
# Lowercase + collapse whitespace + strip the unit prefix is the cleanest
# normalization. We key the map on a canonical "compact" form.
#
# Note: "Saturation Extract EC" and "Bulk EC" are NOT physically the same
# quantity — Bulk EC is the raw sensor measurement; Saturation Extract EC is a
# derived/calibrated value (typically 2–3× larger). The CSV exports only ever
# carried the "Saturation Extract EC" column, so it maps to ``sat_extract_ec``
# — the continuous 2024→now series. "Bulk EC" only appears in XLSX snapshots
# and the ZENTRA Cloud v5 API and maps to ``bulk_ec``. See
# ``bulk_ec_alias_decision`` in memory for the history of this split.
# ---------------------------------------------------------------------------

VARIABLE_MAP: dict[str, str] = {
    # TEROS 12
    "m3/m3 water content":           "moisture",
    "m³/m³ water content":           "moisture",
    "degree_c soil temperature":     "soil_temp",
    "°c soil temperature":           "soil_temp",
    "ms/cm saturation extract ec":   "sat_extract_ec",
    "ms/cm bulk ec":                 "bulk_ec",
    # ATMOS 14
    "degree_c air temperature":      "air_temp",
    "°c air temperature":            "air_temp",
    "rh relative humidity":          "humidity",
    "kpa vapor pressure":            "vapor_pressure",
    "kpa atmospheric pressure":      "atm_pressure",
    "kpa vpd":                       "vpd",
    # ECRN-100
    "mm precipitation":              "precipitation",
    "mm/h max precip rate":          "max_precip_rate",
    # Battery (logger-internal)
    "% battery percent":             "battery_pct",
    "mv battery voltage":            "battery_mv",
    # Barometer (logger-internal)
    "kpa reference pressure":        "ref_pressure",
    "degree_c logger temperature":   "logger_temp",
    "°c logger temperature":         "logger_temp",
}

# Canonical units, indexed by variable name. Used for documentation and
# round-trip checks; not enforced at load time.
VARIABLE_UNITS: dict[str, str] = {
    "moisture":         "m3/m3",
    "soil_temp":        "degC",
    "bulk_ec":          "mS/cm",
    "sat_extract_ec":   "mS/cm",
    "air_temp":         "degC",
    "humidity":         "%RH",
    "vapor_pressure":   "kPa",
    "atm_pressure":     "kPa",
    "vpd":              "kPa",
    "precipitation":    "mm",
    "max_precip_rate":  "mm/h",
    "battery_pct":      "%",
    "battery_mv":       "mV",
    "ref_pressure":     "kPa",
    "logger_temp":      "degC",
}

# ---------------------------------------------------------------------------
# ZENTRA Cloud v5 API measurement names -> canonical variable.
#
# The v5 ``Reading.measurement`` strings are clean and stable, so we key on
# them directly rather than reconstructing a "unit + name" header string.
#
# Differences from the CSV/XLSX exports:
#   * v5 exposes "Bulk EC" and "Saturation Extract EC" as SEPARATE series,
#     mapped to ``bulk_ec`` and ``sat_extract_ec`` respectively — the same
#     split as ``VARIABLE_MAP`` above. ``sat_extract_ec`` is the continuous
#     series (CSV history + v5); ``bulk_ec`` is v5-era only. See
#     ``bulk_ec_alias_decision`` in memory.
#   * "Raw VWC", "Pore Water EC", "Dew Point" and "Signal" have no CSV
#     counterpart and are not used downstream -> dropped.
# ---------------------------------------------------------------------------

V5_MEASUREMENT_MAP: dict[str, str] = {
    "Water Content":          "moisture",
    "Soil Temperature":       "soil_temp",
    "Bulk EC":                "bulk_ec",
    "Saturation Extract EC":  "sat_extract_ec",
    "Air Temperature":        "air_temp",
    "Atmospheric Pressure":   "atm_pressure",
    "Relative Humidity":      "humidity",
    "VPD":                    "vpd",
    "Vapor Pressure":         "vapor_pressure",
    "Precipitation":          "precipitation",
    "Max Precip Rate":        "max_precip_rate",
    "Battery Percent":        "battery_pct",
    "Battery Voltage":        "battery_mv",
    "Reference Pressure":     "ref_pressure",
    "Logger Temperature":     "logger_temp",
}

# v5 measurements we deliberately drop (no CSV counterpart, unused downstream).
V5_DROP_MEASUREMENTS: frozenset[str] = frozenset(
    {"Raw VWC", "Pore Water EC", "Dew Point", "Signal"}
)

# v5 ``sensor_name`` strings -> canonical sensor type. Mostly the same words
# as the CSV/XLSX row-2 labels, minus the trailing description.
V5_SENSOR_TYPE_MAP: dict[str, str] = {
    "TEROS 12":        "TEROS12",
    "ATMOS 14":        "ATMOS14",
    "ECRN-100":        "ECRN100",
    "Battery":         "BATTERY",
    "Barometer":       "BAROMETER",
    "Signal Strength": "SIGNAL",
}


def normalize_v5_sensor_type(raw: str | None) -> str | None:
    """Map a v5 ``Reading.sensor_name`` to a canonical sensor-type token."""
    if not isinstance(raw, str):
        return None
    return V5_SENSOR_TYPE_MAP.get(raw.strip())


def normalize_v5_measurement(raw: str | None) -> str | None:
    """Map a v5 ``Reading.measurement`` to a canonical variable name.

    Returns None for measurements we drop (``V5_DROP_MEASUREMENTS``) or for
    anything unrecognised — the caller decides whether to warn.
    """
    if not isinstance(raw, str):
        return None
    return V5_MEASUREMENT_MAP.get(raw.strip())


# ---------------------------------------------------------------------------
# Port label parser. Excel uses "Port 1" (with space), CSV uses "Port1".
# ---------------------------------------------------------------------------

_PORT_RE = re.compile(r"^\s*Port\s*(\d+)\s*$", re.IGNORECASE)


def parse_port_label(label: str | None) -> int | None:
    """Return the integer port number from a 'Port N' or 'PortN' label.

    Returns None for the timestamp column or anything that doesn't match.
    """
    if not isinstance(label, str):
        return None
    m = _PORT_RE.match(label)
    return int(m.group(1)) if m else None


def normalize_sensor_type(raw: str | None) -> str | None:
    """Map a sensor-type cell (row 2 of the header) to a canonical token.

    Returns None for cells that are not a known sensor type (e.g. the
    'Records: N' cell in column 0).
    """
    if not isinstance(raw, str):
        return None
    return SENSOR_TYPE_MAP.get(raw.strip().lower())


def normalize_variable(raw: str | None) -> str | None:
    """Map a unit+meaning cell (row 3 of the header) to a canonical variable.

    Whitespace is collapsed and the string is lowercased before lookup.
    Returns None for unknown strings (caller decides whether to warn or drop).
    """
    if not isinstance(raw, str):
        return None
    key = " ".join(raw.split()).lower()
    return VARIABLE_MAP.get(key)


# ---------------------------------------------------------------------------
# Filename → logger serial. Both CSV folders and Excel filenames follow the
# pattern "z6-NNNNN ...".
# ---------------------------------------------------------------------------

_LOGGER_RE = re.compile(r"z6-(\d{5})", re.IGNORECASE)


def logger_serial_from_name(name: str) -> str | None:
    """Extract the 5-digit logger serial from a filename like 'z6-19570 ...'."""
    m = _LOGGER_RE.search(name)
    return m.group(1) if m else None
