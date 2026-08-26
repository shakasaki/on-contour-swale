"""Fast loading / concatenation layer for the OhmPi resistivity campaign.

Three layers, cheapest first:

1. build_survey_index()  -> one row per survey (timestamp, array, line, paths)
2. build_summary_table() -> concat of every instrument `_results.csv`, one row per
   (survey, quadrupole), with reciprocal error attached. Small, cached as parquet.
3. load_waveforms(quads) -> stream the `_fw.zip`s once, keep only the requested
   quadrupoles, concat across the whole campaign with a `timestamp` column.

Data lives at  <repo>/data/ohmpi/<year>/<YYYYMMDD>/  and each survey is a pair:
    <array>_line_<L>_results_<stamp>.csv        (instrument summary, ~14 KB)
    <array>_line_<L>_results_<stamp>_fw.zip     (full waveform, contains _fw.csv)
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "ohmpi"
CACHE_DIR = REPO_ROOT / "ohmpi" / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# dipdip_line_A_results_20250408T235131[_fw]
FNAME_RE = re.compile(
    r"(?P<array>dipdip|wenner)_line_(?P<line>[A-E])_results_(?P<stamp>\d{8}T\d{6})"
)


def build_survey_index() -> pl.DataFrame:
    """One row per survey, sorted by time. Keyed off the timestamped `_fw.zip`s."""
    rows = []
    for zip_path in DATA_DIR.rglob("*_fw.zip"):
        m = FNAME_RE.search(zip_path.name)
        if not m:
            continue
        results_csv = zip_path.with_name(zip_path.name.replace("_fw.zip", ".csv"))
        rows.append(
            {
                "array": m["array"],
                "line": m["line"],
                "stamp": m["stamp"],
                "fw_zip": str(zip_path),
                "results_csv": str(results_csv) if results_csv.exists() else None,
            }
        )
    return (
        pl.DataFrame(rows)
        .with_columns(
            pl.col("stamp").str.strptime(pl.Datetime, "%Y%m%dT%H%M%S").alias("timestamp")
        )
        .sort("timestamp")
    )


def _quad_col() -> pl.Expr:
    return pl.concat_str(
        [pl.col("a"), pl.col("b"), pl.col("m"), pl.col("n")], separator="_"
    ).alias("quad")


def build_summary_table(index: pl.DataFrame | None = None) -> pl.DataFrame:
    """Concat every instrument `_results.csv` into one tidy frame, add reciprocal error.

    One row per (survey, quadrupole). Columns kept: timestamp, array, line, quad,
    a,b,m,n, r, vmn, iab, r_std_pct, vmn_std_pct, sp, rab, and recip_err_pct
    (relative |R_fwd - R_rec| within the same survey, where the reciprocal m_n_a_b
    was also measured).
    """
    if index is None:
        index = build_survey_index()

    keep = {
        "a": "a", "b": "b", "m": "m", "n": "n",
        "r_[Ohm]": "r", "vmn_[mV]": "vmn", "iab_[mA]": "iab",
        "r_std_[%]": "r_std_pct", "vmn_std_[%]": "vmn_std_pct",
        "sp_[mV]": "sp", "rab_[kOhm]": "rab",
    }

    frames = []
    for row in index.filter(pl.col("results_csv").is_not_null()).iter_rows(named=True):
        df = pl.read_csv(row["results_csv"], infer_schema_length=2000)
        present = {k: v for k, v in keep.items() if k in df.columns}
        # some files carry literal 'nan'/'inf' in the std columns -> force numeric
        num_cols = [c for c in ("r", "vmn", "iab", "r_std_pct",
                                "vmn_std_pct", "sp", "rab") if c in present.values()]
        df = (
            df.select(list(present.keys()))
            .rename(present)
            .with_columns(pl.col(c).cast(pl.Float64, strict=False) for c in num_cols)
            .with_columns(
                pl.lit(row["timestamp"]).alias("timestamp"),
                pl.lit(row["array"]).alias("array"),
                pl.lit(row["line"]).alias("line"),
            )
            .with_columns(_quad_col())
            .with_columns(
                pl.concat_str(
                    [pl.col("m"), pl.col("n"), pl.col("a"), pl.col("b")], separator="_"
                ).alias("recip_quad")
            )
        )
        # reciprocal error within this survey
        rec = df.select(["quad", "r"]).rename({"quad": "recip_quad", "r": "r_rec"})
        df = df.join(rec, on="recip_quad", how="left").with_columns(
            (
                (pl.col("r") - pl.col("r_rec")).abs()
                / ((pl.col("r") + pl.col("r_rec")).abs() / 2)
                * 100
            ).alias("recip_err_pct")
        )
        frames.append(df)

    return pl.concat(frames, how="diagonal_relaxed").sort(["timestamp", "array", "line"])


def load_waveforms(quads: list[str], index: pl.DataFrame | None = None) -> pl.DataFrame:
    """Stream every `_fw.zip` once, keep only `quads`, concat across the campaign.

    Returns one long frame: timestamp, array, line, quad, a,b,m,n, injection_id,
    channel_mn, time, current, voltage, polarity.
    """
    if index is None:
        index = build_survey_index()
    want = set(quads)

    frames = []
    bad = []
    for row in index.iter_rows(named=True):
        try:
            with zipfile.ZipFile(row["fw_zip"]) as zf:
                members = [n for n in zf.namelist() if n.endswith("_fw.csv")]
                if not members:
                    continue
                raw = zf.read(members[0])
        except zipfile.BadZipFile:
            bad.append(row["fw_zip"])
            continue
        df = pl.read_csv(io.BytesIO(raw))
        df = df.with_columns(_quad_col()).filter(pl.col("quad").is_in(list(want)))
        if df.height == 0:
            continue
        df = df.with_columns(
            pl.lit(row["timestamp"]).alias("timestamp"),
            pl.lit(row["array"]).alias("array"),
            pl.lit(row["line"]).alias("line"),
        )
        frames.append(df)

    if bad:
        print(f"WARNING: skipped {len(bad)} unreadable zip(s):")
        for b in bad:
            print(f"  {b}")
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed").sort(["quad", "timestamp", "time"])


if __name__ == "__main__":
    idx = build_survey_index()
    idx.write_parquet(CACHE_DIR / "survey_index.parquet")
    print(f"survey index: {idx.height} surveys")
    print(idx.group_by("array", "line").len().sort("array", "line"))
    print("date span:", idx["timestamp"].min(), "->", idx["timestamp"].max())

    summary = build_summary_table(idx)
    summary.write_parquet(CACHE_DIR / "summary_table.parquet")
    print(f"\nsummary table: {summary.height} (survey x quad) rows")
    print(summary.head())
