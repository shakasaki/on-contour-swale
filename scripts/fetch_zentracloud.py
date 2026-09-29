"""Pull raw sensor readings from the ZENTRA Cloud v5 API for the three ZL6
loggers at the site (05511 control, 19570 top, 19574 bottom), as an
alternative to manually exporting a CSV dump from the web portal.

Verified against a live v5 account on 2026-08-28 (account migrated to
ZENTRA Cloud 2.0). Device IDs confirmed via ``client.v5.devices.list()``:
``z6-05511`` (control), ``z6-19570`` (top), ``z6-19574`` (bottom); the
``z6-05533`` Forest logger exists but is deliberately excluded, matching the
loader.

Writes one long-format parquet per logger to ``data/zentracloud/``:
``device_id, datetime, timestamp, port_num, sensor_name, measurement,
value, unit, error_code`` (the raw ``Reading`` fields from the SDK — not yet
mapped onto ``swale``'s canonical ``variable``/``sensor_type`` schema used by
``read_logger_csv``; do that mapping when actually wiring this into the
loader).

Auth: set ``ZENTRACLOUD_API_KEY`` (get it from ZENTRA Cloud -> Profile ->
Integrations -> Show Token, https://app.zentracloud.io/profile/integrations).

Usage::

    ZENTRACLOUD_API_KEY=... PYTHONPATH=src python3 scripts/fetch_zentracloud.py
    ZENTRACLOUD_API_KEY=... python3 scripts/fetch_zentracloud.py --window 7d
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl
from zentracloud import ZentraClient

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "zentracloud"

DEVICE_IDS = {
    "05511": "z6-05511",  # control
    "19570": "z6-19570",  # top
    "19574": "z6-19574",  # bottom
}

READING_FIELDS = (
    "device_id",
    "datetime",
    "timestamp",
    "port_num",
    "sensor_name",
    "measurement",
    "value",
    "unit",
    "error_code",
)


def fetch_logger(client: ZentraClient, device_id: str, **time_kwargs) -> pl.DataFrame:
    rows = [
        {f: getattr(r, f) for f in READING_FIELDS}
        for r in client.v5.devices.iter_data(device_id=device_id, **time_kwargs)
    ]
    return pl.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", help="ISO date/datetime, epoch seconds, or omit for all history")
    ap.add_argument("--end", help="ISO date/datetime or epoch seconds")
    ap.add_argument("--window", help="relative window, e.g. '24h', '7d', '4w' (max 1 year)")
    args = ap.parse_args()

    time_kwargs = {}
    if args.window:
        time_kwargs["window"] = args.window
    else:
        if args.start:
            time_kwargs["start"] = args.start
        if args.end:
            time_kwargs["end"] = args.end

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with ZentraClient() as client:  # reads ZENTRACLOUD_API_KEY from env
        for serial, device_id in DEVICE_IDS.items():
            print(f"Fetching {device_id}...")
            df = fetch_logger(client, device_id, **time_kwargs)
            out = OUT_DIR / f"{serial}.parquet"
            df.write_parquet(out)
            print(f"  {len(df)} readings -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
