"""Pull raw sensor readings from the legacy ZENTRA Cloud v4 REST API
(``/api/v4/get_readings/``) for the three ZL6 loggers at the site (05511
control, 19570 top, 19574 bottom), as an alternative to manually exporting a
CSV dump from the web portal.

Use this instead of ``fetch_zentracloud.py`` (the v5 SDK) while the account
is still on the legacy platform.

Writes one long-format parquet per logger to ``data/zentracloud/``, columns:
``measurement, device_sn, device_name, port_number, sensor_sn, sensor_name,
units, timestamp_utc, datetime, value, precision, mrid, error_flag,
error_description``. Not yet mapped onto ``swale``'s canonical
``variable``/``sensor_type`` schema used by ``read_logger_csv`` — do that
mapping when actually wiring this into the loader.

UNVERIFIED against a live response (no working account at the time this was
written — https://docs.zentracloud.io/l/en/article/gbv2iyxhar-api-v-3-0-us
was the only source). In particular the pagination loop assumes an empty/
missing "data" key means "no more pages"; confirm that against a real
response and adjust ``_iter_pages`` if the API actually reports total pages
some other way.

Auth: set ``ZENTRACLOUD_TOKEN`` (ZENTRA Cloud -> API menu -> Keys tab ->
Copy token). Rate limit: 60 calls/min total, 1 call/min per device — the
three loggers are fetched sequentially with a 1-minute gap to stay under
that.

Usage::

    ZENTRACLOUD_TOKEN=... python3 scripts/fetch_zentracloud_legacy.py
    ZENTRACLOUD_TOKEN=... python3 scripts/fetch_zentracloud_legacy.py \\
        --start-date "2026-08-01 00:00" --end-date "2026-08-26 00:00"
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import polars as pl
import requests

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "zentracloud"

BASE_URL = "https://zentracloud.com/api/v4/get_readings/"
PER_PAGE = 2000  # API max
PER_DEVICE_COOLDOWN_S = 60  # rate limit: 1 call/min per device

DEVICE_SNS = {
    "05511": "z6-05511",  # control
    "19570": "z6-19570",  # top
    "19574": "z6-19574",  # bottom
}


def _iter_pages(token: str, device_sn: str, **params) -> list[dict]:
    """All pages of the 'data' dict for one device, merged measurement-wise."""
    merged: dict[str, list[dict]] = {}
    page_num = 1
    while True:
        resp = requests.get(
            BASE_URL,
            headers={"Authorization": f"Token {token}"},
            params={
                "device_sn": device_sn,
                "output_format": "json",
                "per_page": PER_PAGE,
                "page_num": page_num,
                **params,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or {}
        if not data:
            break
        for measurement, blocks in data.items():
            merged.setdefault(measurement, []).extend(blocks)
        # Bail once a page comes back with fewer readings than the page size
        # for every measurement (no documented "more pages" flag to check).
        max_readings = max((len(b["readings"]) for blocks in data.values() for b in blocks), default=0)
        if max_readings < PER_PAGE:
            break
        page_num += 1
    return merged


def flatten(device_sn: str, data: dict[str, list[dict]]) -> pl.DataFrame:
    rows = []
    for measurement, blocks in data.items():
        for block in blocks:
            meta = block.get("metadata", {})
            for r in block.get("readings", []):
                rows.append(
                    {
                        "measurement": measurement,
                        "device_sn": meta.get("device_sn", device_sn),
                        "device_name": meta.get("device_name"),
                        "port_number": meta.get("port_number"),
                        "sensor_sn": meta.get("sensor_sn"),
                        "sensor_name": meta.get("sensor_name"),
                        "units": meta.get("units"),
                        "timestamp_utc": r.get("timestamp_utc"),
                        "datetime": r.get("datetime"),
                        "value": r.get("value"),
                        "precision": r.get("precision"),
                        "mrid": r.get("mrid"),
                        "error_flag": r.get("error_flag"),
                        "error_description": r.get("error_description"),
                    }
                )
    return pl.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start-date", help="'YYYY-MM-DD HH:MM', omit for all history")
    ap.add_argument("--end-date", help="'YYYY-MM-DD HH:MM'")
    args = ap.parse_args()

    token = os.environ.get("ZENTRACLOUD_TOKEN")
    if not token:
        raise SystemExit("Set ZENTRACLOUD_TOKEN")

    date_params = {}
    if args.start_date:
        date_params["start_date"] = args.start_date
    if args.end_date:
        date_params["end_date"] = args.end_date

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for i, (serial, device_sn) in enumerate(DEVICE_SNS.items()):
        print(f"Fetching {device_sn}...")
        data = _iter_pages(token, device_sn, **date_params)
        df = flatten(device_sn, data)
        out = OUT_DIR / f"{serial}.parquet"
        df.write_parquet(out)
        print(f"  {len(df)} readings -> {out.relative_to(ROOT)}")
        if i < len(DEVICE_SNS) - 1:
            time.sleep(PER_DEVICE_COOLDOWN_S)


if __name__ == "__main__":
    main()
