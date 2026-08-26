"""Display-label mapping for the SMS sensors.

The raw `SMSnn` IDs come from the METER ZL6 metadata and are not
informative for figure labels. This module provides a single source
of truth for the *display* name to use on plot axes, legends, and
tables — encoding treatment, slope position, and depth in the label
itself.

Convention
----------
    {treatment}_{position}_{depth_cm}

with:
    treatment  = "sw"  (swale)    | "cn" (control)
    position   = "t"   (top)      | "m" (middle / Mound on the swale,
                                          Mid on the control)
                                  | "b"  (bottom — control only)
                                  | "b1" / "b2" (the two swale
                                          bottom-slope pairs)
                                  | "s"  (Step — swale only)
    depth_cm   = "10"  | "40"

Examples
--------
    SMS04 → sw_m_10   (swale Mound, 10 cm)
    SMS07 → sw_b1_40  (swale Bottom 1, 40 cm)
    SMS10 → sw_s_40   (swale Step, 40 cm only)
    SMS14 → cn_m_40   (control Mid, 40 cm)

SMS03 has no display name — its metadata depth is recorded as
-10 cm (likely a data-entry error in the source XLSX) and it is
excluded from the slope-paired analyses already. Calling
`display(name)` on "SMS03" returns the raw ID with a `?` suffix so
the anomaly is visible if it ever turns up in a plot.

The mapping is internal-only: cached parquet, scripts that work with
the long-form data, the metadata file, and the slope-grouping
configs all still key on `SMSnn`. Only the display layer changes.
"""

from __future__ import annotations

# Canonical mapping. Order is by slope position then depth for
# readability when this file is opened by hand.
SENSOR_DISPLAY: dict[str, str] = {
    # Swale — Top slope (SwB)
    "SMS01": "sw_t_10",
    "SMS02": "sw_t_40",
    # Swale — Mound (SwD)
    "SMS04": "sw_m_10",
    "SMS05": "sw_m_40",
    # Swale — Bottom 1 (SwE)
    "SMS06": "sw_b1_10",
    "SMS07": "sw_b1_40",
    # Swale — Bottom 2 (SwF)
    "SMS08": "sw_b2_10",
    "SMS09": "sw_b2_40",
    # Swale — Step
    "SMS10": "sw_s_40",
    # Control — Top (ConG)
    "SMS11": "cn_t_10",
    "SMS12": "cn_t_40",
    # Control — Mid (ConH)
    "SMS13": "cn_m_10",
    "SMS14": "cn_m_40",
    # Control — Bottom (ConI)
    "SMS15": "cn_b_10",
    "SMS16": "cn_b_40",
    # SMS03 deliberately omitted (depth = -10 cm metadata anomaly).
}


def display(sensor_id: str) -> str:
    """Return the display label for a raw SMS sensor ID.

    If the ID is not in the canonical mapping (SMS03, weather
    sensors, ATMOS-14, ECRN-100, etc.), return the raw ID with a
    `?` suffix so anomalies are visible.
    """
    if sensor_id in SENSOR_DISPLAY:
        return SENSOR_DISPLAY[sensor_id]
    return f"{sensor_id}?"


def display_with_raw(sensor_id: str) -> str:
    """Return `display (raw)` form — useful for transitional labels.

    Example: `sw_b1_40 (SMS07)`.
    """
    d = display(sensor_id)
    return f"{d} ({sensor_id})"
