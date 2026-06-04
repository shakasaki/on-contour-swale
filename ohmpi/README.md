# OhmPi resistivity workstream

Processing + interactive browsing of the OhmPi campaign (raw `_fw.zip` waveforms
in `data/ohmpi/`).

## Build the caches first

The derived caches under `ohmpi/cache/` are **gitignored** (the waveform cache
alone is ~920 MB), so a fresh checkout has none of them and the browser fails to
load with `FileNotFoundError: ... r_table.parquet`. Build them once:

```bash
conda activate swale
python ohmpi/scripts/build_all.py        # add --force to rebuild existing caches
```

This streams the 2497 raw zips and writes:

| cache | built by | what it is |
|-------|----------|------------|
| `ohmpi/cache/r_table.parquet` | `build_r_table.py` | per-(survey × quad) R, R_rec, ρ_a, recip error, `keep`/`drop_day` QC flags (lines A–D) |
| `ohmpi/cache/waveforms/<array>_<line>/<quad>.parquet` | `build_waveform_cache.py` | every raw V/I sample per quad, across the campaign (lines A–E) |

`build_all.py` skips any cache that already exists; pass `--force` to rebuild.

## Run the browser

```bash
bokeh serve --show ohmpi/scripts/ohmpi_browser.py
```

Array → line → quad dropdowns. Per quad: raw V/I square wave for a chosen
survey, decimated campaign voltage scatter, R/R_rec/ρ_a coloured by `keep`, and
reciprocal-error vs time with the 5 % / 15 % QC lines. r_table covers A–D only,
so line E shows raw waveforms with empty R/QC panels.
