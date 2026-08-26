"""Build a per-quad waveform cache for the interactive browser.

Streams every `_fw.zip` in the campaign exactly once and writes one parquet per
`(array, line, quad)` under `ohmpi/cache/waveforms/`. The Bokeh server app
(`ohmpi_browser.py`) then reads only the selected quad's file on demand, so a
quad swap is a single small parquet read instead of re-streaming ~2500 zips.

Layout:
    ohmpi/cache/waveforms/<array>_<line>/<quad>.parquet

Each file holds every raw sample for that quad across the whole campaign:
    timestamp, injection_id, channel_mn, time, current, voltage, polarity
sorted by (timestamp, time). A quad's `(array, line)` is implied by its folder,
which is why we partition on all three (2 channel-quads recur across arrays).
"""

from __future__ import annotations

import io
import zipfile

import polars as pl

from ohmpi_loader import CACHE_DIR, build_survey_index, _quad_col

WF_DIR = CACHE_DIR / "waveforms"

# columns kept per sample (a,b,m,n are redundant with `quad`; dropped to save space)
KEEP = ["timestamp", "array", "line", "quad",
        "injection_id", "channel_mn", "time", "current", "voltage", "polarity"]


def read_one(row: dict) -> pl.DataFrame | None:
    """Read + tag a single survey's `_fw.csv`; None if the zip is unreadable/empty."""
    try:
        with zipfile.ZipFile(row["fw_zip"]) as zf:
            members = [m for m in zf.namelist() if m.endswith("_fw.csv")]
            if not members:
                return None
            raw = zf.read(members[0])
    except zipfile.BadZipFile:
        return None
    return (
        pl.read_csv(io.BytesIO(raw))
        .with_columns(_quad_col())
        .with_columns(
            pl.lit(row["timestamp"]).alias("timestamp"),
            pl.lit(row["array"]).alias("array"),
            pl.lit(row["line"]).alias("line"),
        )
        .select(KEEP)
    )


def build(index: pl.DataFrame) -> tuple[int, int]:
    """Process one (array, line) group at a time to bound peak memory.

    Returns (n_quad_files, n_bad_zips).
    """
    if WF_DIR.exists():
        for p in sorted(WF_DIR.rglob("*.parquet")):
            p.unlink()
    WF_DIR.mkdir(parents=True, exist_ok=True)

    n_files, bad = 0, []
    groups = index.group_by(["array", "line"]).agg(pl.len()).sort(["array", "line"])
    for array, line, _ in groups.iter_rows():
        grp = index.filter((pl.col("array") == array) & (pl.col("line") == line))
        frames = []
        for row in grp.iter_rows(named=True):
            df = read_one(row)
            if df is None:
                bad.append(row["fw_zip"])
            elif df.height:
                frames.append(df)
        if not frames:
            continue
        wf = pl.concat(frames, how="diagonal_relaxed")
        out_dir = WF_DIR / f"{array}_{line}"
        out_dir.mkdir(parents=True, exist_ok=True)
        per_quad = wf.partition_by("quad", as_dict=True)
        for (quad,), sub in per_quad.items():
            sub.sort(["timestamp", "time"]).write_parquet(out_dir / f"{quad}.parquet")
        n_files += len(per_quad)
        print(f"  {array} line {line}: {grp.height} surveys, "
              f"{wf.height:,} rows -> {len(per_quad)} quad files", flush=True)
        del frames, wf, per_quad

    if bad:
        print(f"WARNING: skipped {len(bad)} unreadable zip(s)", flush=True)
    return n_files, len(bad)


if __name__ == "__main__":
    idx = build_survey_index()
    print(f"streaming {idx.height} surveys, grouped by (array, line) ...", flush=True)
    n_files, n_bad = build(idx)
    total_mb = sum(p.stat().st_size for p in WF_DIR.rglob("*.parquet")) / 1e6
    print(f"wrote {n_files} per-quad files to {WF_DIR}  ({total_mb:.1f} MB), "
          f"{n_bad} bad zip(s)", flush=True)
