from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from swale.metadata import parse_metadata
from tests.conftest import make_metadata_fixture


def test_parse_metadata_extracts_sensors_and_skips_forest(tmp_path: Path):
    md = make_metadata_fixture(tmp_path / "Metadata.xlsx")
    sensors, ports = parse_metadata(md)
    sids = sorted(sensors["sensor_id"].to_list())
    # The Forest sensor SMS17 must be filtered out; the swale + control
    # sensors are kept.
    assert "SMS17" not in sids
    assert sids == ["SMS01", "SMS02", "SMS11"]
    assert sensors.filter(pl.col("sensor_id") == "SMS01")["treatment"].item() == "swale"
    assert sensors.filter(pl.col("sensor_id") == "SMS11")["treatment"].item() == "control"


def test_parse_metadata_normalizes_sms_ids(tmp_path: Path):
    md = make_metadata_fixture(tmp_path / "Metadata.xlsx")
    sensors, ports = parse_metadata(md)
    # Source spreadsheet writes 'SMS1' and 'SMS 16' inconsistently; the
    # parser normalizes to zero-padded 'SMS01', 'SMS16', etc.
    assert "SMS1" not in sensors["sensor_id"].to_list()
    assert "SMS01" in sensors["sensor_id"].to_list()


def test_parse_metadata_synthesizes_internal_ports(tmp_path: Path):
    md = make_metadata_fixture(tmp_path / "Metadata.xlsx")
    _, ports = parse_metadata(md)
    # Battery on port 7, Barometer on port 8 are added for every logger
    # in NON_FOREST_LOGGERS (regardless of whether the synthetic fixture
    # mentions them — they always exist on the physical loggers).
    types = sorted(set(ports["sensor_type"].to_list()))
    assert "BATTERY" in types
    assert "BAROMETER" in types
    # Forest logger 05533 is never in the port mapping.
    assert "05533" not in ports["logger_serial"].to_list()


def test_parse_metadata_missing_sheet_raises(tmp_path: Path):
    import openpyxl
    p = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    wb.save(p)
    wb.close()
    with pytest.raises(ValueError, match="Serials"):
        parse_metadata(p)


def test_parse_metadata_real_file_smoke():
    """Sanity-check against the real Metadata.xlsx if it exists.

    This test exercises the actual messy upstream spreadsheet rather than
    the synthetic fixture; it's the only place we lock in the real shape
    (18 non-Forest sensors, 24 ports).
    """
    from swale.config import load_settings

    real = load_settings().metadata_xlsx
    if not real.exists():
        pytest.skip("Real Metadata.xlsx not present in this checkout")
    sensors, ports = parse_metadata(real)
    assert sensors.height == 18
    # 16 TEROS port slots + 6 internal (3 loggers x 2) + ATMOS + ECRN.
    assert ports.height == 16 + 6 + 2
