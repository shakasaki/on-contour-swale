from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from swale.loader import load_swale_dataset
from tests.conftest import (
    make_csv_fixture,
    make_metadata_fixture,
    make_xlsx_fixture,
)


def _build_minimal_dataset(tmp_path: Path) -> tuple[Path, Path]:
    """Lay out a tiny but realistic data_root + Metadata.xlsx."""
    data_root = tmp_path / "data"
    (data_root / "19570").mkdir(parents=True)
    (data_root / "data_xlsx").mkdir(parents=True)
    (data_root / "05511").mkdir()
    md = make_metadata_fixture(data_root / "Metadata.xlsx")
    return data_root, md


def test_loader_dedup_prefers_xlsx_on_overlap(tmp_path: Path):
    data_root, md = _build_minimal_dataset(tmp_path)

    # CSV reports rounded values; XLSX has full precision. Both contain
    # the same timestamp.
    make_csv_fixture(
        data_root / "19570" / "z6-19570 - top(z6-19570)-Configuration 1-X.csv",
        rows=[(
            "25/05/2024 01:15:00",
            0.300, 18.5, 1.20, 22.0, 1.5, 95.0, 0.0, 0.0,
            100, 8000, 95.0, 24.0,
        )],
    )
    make_xlsx_fixture(
        data_root / "data_xlsx" / "z6-19570 25May24-0115.xlsx",
        sheets={"Config 1": [(
            datetime(2024, 5, 25, 1, 15),
            0.301234, 18.5, 1.20,           # TEROS 12 (full precision)
            100, 8000, 95.0, 24.0,           # battery, barometer
        )]},
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(data_root, md, grid="none")
    sub = df.filter((pl.col("variable") == "moisture")
                    & (pl.col("sensor_id") == "SMS01"))
    assert sub.height == 1
    # Full-precision XLSX value retained, not the rounded CSV one.
    assert sub["value"].item() == pytest.approx(0.301234)
    assert sub["source_format"].item() == "xlsx"


def test_loader_emits_warning_on_disagreement(tmp_path: Path):
    data_root, md = _build_minimal_dataset(tmp_path)
    # CSV vs XLSX disagree well beyond tolerance on the same timestamp.
    make_csv_fixture(
        data_root / "19570" / "z6-19570 - top(z6-19570)-Configuration 1-X.csv",
        rows=[("25/05/2024 01:15:00",
                 0.300, 18.5, 1.20, 22.0, 1.5, 95.0, 0.0, 0.0,
                 100, 8000, 95.0, 24.0)],
    )
    make_xlsx_fixture(
        data_root / "data_xlsx" / "z6-19570 25May24-0115.xlsx",
        sheets={"Config 1": [(datetime(2024, 5, 25, 1, 15),
                                0.500, 18.5, 1.20, 100, 8000, 95.0, 24.0)]},
    )
    with pytest.warns(UserWarning, match="disagreeing"):
        load_swale_dataset(data_root, md, grid="none")


def test_loader_drops_implausible_timestamps(tmp_path: Path):
    data_root, md = _build_minimal_dataset(tmp_path)
    make_xlsx_fixture(
        data_root / "data_xlsx" / "z6-19570 27Mar24-1812.xlsx",
        sheets={"Config 1": [
            # A logger-clock-glitch row in 2099 alongside a valid 2024 row.
            (datetime(2099, 11, 29, 19, 15), 0.30, 18.5, 1.20,
             82, 7656, 95.4, 22.7),
            (datetime(2024, 5, 25, 1, 15), 0.31, 18.6, 1.21,
             100, 8000, 95.0, 24.0),
        ]},
    )
    with pytest.warns(UserWarning, match="implausible timestamps"):
        df = load_swale_dataset(data_root, md, grid="none")
    assert df["timestamp"].max().year < 2030


def test_loader_writes_and_reads_cache(tmp_path: Path):
    data_root, md = _build_minimal_dataset(tmp_path)
    make_xlsx_fixture(
        data_root / "data_xlsx" / "z6-19570 25May24.xlsx",
        sheets={"Config 1": [
            (datetime(2024, 5, 25, 1, 15), 0.31, 18.6, 1.21,
             100, 8000, 95.0, 24.0),
        ]},
    )
    cache = tmp_path / "cache"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df1 = load_swale_dataset(data_root, md, grid="none", cache_dir=cache)
        # Second call returns cache without re-reading source files.
        df2 = load_swale_dataset(data_root, md, grid="none", cache_dir=cache)
    assert df1.height == df2.height
    assert sorted(cache.glob("logger=*.parquet"))


def test_loader_reindex_inserts_nulls(tmp_path: Path):
    data_root, md = _build_minimal_dataset(tmp_path)
    # Two timestamps with a 30-min gap; we ask for a 15-min grid -> 1 null in middle.
    make_xlsx_fixture(
        data_root / "data_xlsx" / "z6-19570 25May24.xlsx",
        sheets={"Config 1": [
            (datetime(2024, 5, 25, 1, 0), 0.30, 18.5, 1.20,
             100, 8000, 95.0, 24.0),
            (datetime(2024, 5, 25, 1, 30), 0.32, 18.6, 1.22,
             100, 8000, 95.0, 24.1),
        ]},
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(data_root, md, grid="15m")
    moisture = (df.filter((pl.col("variable") == "moisture")
                          & (pl.col("sensor_id") == "SMS01"))
                  .sort("timestamp"))
    assert moisture.height == 3  # 01:00, 01:15, 01:30
    assert moisture["value"].to_list() == [pytest.approx(0.30),
                                             None,
                                             pytest.approx(0.32)]


@pytest.mark.slow
def test_loader_real_dataset_smoke():
    """End-to-end smoke against the user's real /home/alexis/DATA/swale tree."""
    data_root = Path("/home/alexis/DATA/swale")
    md = data_root / "Metadata.xlsx"
    if not md.exists():
        pytest.skip("Real dataset not present in this checkout")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = load_swale_dataset(data_root, md, grid="none")
    # All three non-Forest loggers must be present.
    assert sorted(df["logger_serial"].unique().to_list()) == ["05511",
                                                                "19570",
                                                                "19574"]
    # Forest logger must be absent.
    assert "05533" not in df["logger_serial"].to_list()
    # ATMOS / ECRN are unique to logger 19570.
    atmos = df.filter(pl.col("sensor_type") == "ATMOS14")
    assert atmos["logger_serial"].unique().to_list() == ["19570"]
    ecrn = df.filter(pl.col("sensor_type") == "ECRN100")
    assert ecrn["logger_serial"].unique().to_list() == ["19570"]
    # Plausible date range — no impossible timestamps survive.
    assert df["timestamp"].min().year >= 2020
    assert df["timestamp"].max().year <= 2030
