from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

from swale.readers import read_logger_csv, read_logger_xlsx
from tests.conftest import make_csv_fixture, make_xlsx_fixture


def test_read_logger_csv_long_format(tmp_path: Path):
    p = tmp_path / "z6-19570 - top(z6-19570)-Configuration 1-X.csv"
    make_csv_fixture(p, rows=[
        ("25/05/2024 01:15:00", 0.30, 18.5, 1.20, 22.0, 1.5, 95.0, 0.0, 0.0,
         100, 8000, 95.0, 24.0),
        ("25/05/2024 01:30:00", 0.31, 18.7, 1.21, 22.1, 1.5, 95.1, 0.2, 1.0,
         100, 8001, 95.0, 24.1),
    ])
    df = read_logger_csv(p)
    assert df.height > 0
    assert set(df.columns) == {"timestamp", "port", "sensor_type", "variable",
                                 "value", "source_format", "source_file",
                                 "config_label"}
    assert df["source_format"].unique().to_list() == ["csv"]
    # Two timestamps × (3 TEROS + 3 ATMOS + 2 ECRN + 2 BATT + 2 BARO) = 24.
    assert df.height == 24
    # The timestamp parse should yield real datetimes.
    assert df["timestamp"].min() == datetime(2024, 5, 25, 1, 15)
    # config_label round-trip.
    assert df["config_label"].unique().to_list() == ["Configuration 1"]


def test_read_logger_csv_drops_unknown_sensor_type(tmp_path: Path):
    """Sensor types we don't map (e.g. 'Unrecognized') are filtered out."""
    p = tmp_path / "z6-19570 - top(z6-19570)-Configuration 1-X.csv"
    # Manually write a CSV whose Port 4 advertises an Unrecognized sensor.
    p.write_text(
        "z6-19570,Port1,Port1,Port1,Port4\n"
        "# Records: 1,TEROS 12 Moisture/Temp/EC,TEROS 12 Moisture/Temp/EC,"
        "TEROS 12 Moisture/Temp/EC,Unrecognized\n"
        "Timestamps, m3/m3 Water Content, degree_C Soil Temperature,"
        " mS/cm Saturation Extract EC, Sensor Output\n"
        "01/06/2024 12:00:00,0.40,20.0,1.5,99999\n",
        encoding="utf-8",
    )
    df = read_logger_csv(p)
    # 3 TEROS variables only; the Unrecognized column is dropped.
    assert df.height == 3
    assert set(df["variable"].to_list()) == {"moisture", "soil_temp", "bulk_ec"}


def test_read_logger_csv_handles_unsorted_and_blank_rows(tmp_path: Path):
    p = tmp_path / "z6-05511 - control(z6-05511)-Configuration 1-X.csv"
    make_csv_fixture(p, logger_name="z6-05511", rows=[
        ("25/05/2024 02:00:00", 0.31, 18.7, 1.21, 22.1, 1.5, 95.1, 0.2, 1.0,
         100, 8001, 95.0, 24.1),
        ("25/05/2024 01:15:00", 0.30, 18.5, 1.20, 22.0, 1.5, 95.0, 0.0, 0.0,
         100, 8000, 95.0, 24.0),
        ("", "", "", "", "", "", "", "", "", "", "", "", ""),  # blank
    ])
    df = read_logger_csv(p)
    # Blank row dropped by the timestamp filter; two valid timestamps remain.
    assert df["timestamp"].n_unique() == 2


def test_read_logger_xlsx_multiple_sheets(tmp_path: Path):
    p = tmp_path / "z6-19570 02Aug24-1459.xlsx"
    make_xlsx_fixture(p, sheets={
        "Config 1": [
            (datetime(2024, 5, 25, 1, 0), 0.30, 18.5, 1.20, 100, 8000, 95.0, 24.0),
        ],
        "Config 2": [
            (datetime(2024, 5, 25, 2, 0), 0.31, 18.6, 1.21, 100, 8001, 95.0, 24.1),
        ],
    })
    df = read_logger_xlsx(p)
    assert sorted(df["config_label"].unique().to_list()) == ["Config 1", "Config 2"]
    assert df["source_format"].unique().to_list() == ["xlsx"]
    # 2 timestamps × 7 active variables (3 TEROS + 2 BATT + 2 BARO) = 14.
    assert df.height == 14
