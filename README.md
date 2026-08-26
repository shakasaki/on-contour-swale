# on-contour-swale

Soil moisture, drainage, and surface-elevation analysis for the
**Sadhana Forest** swale site in Auroville, southern India. A swale is
a shallow ditch dug along an elevation contour; the working hypothesis
under test here is that, compared to an adjacent control hillslope,
the swale captures rainwater, slows it down, and lets it infiltrate
locally — moderating runoff during the monsoon and keeping the upper
soil column wetter into the dry season.

The data are 5-minute TEROS-12 readings from 8 sensor pairs (5 in the
swale, 3 in the control) installed at 10 cm and 40 cm depth, plus an
ATMOS-14 weather station and a tipping-bucket rain gauge on the same
site. A ground-based LiDAR survey of the site is also included
(`data/DEM/`, `data/DEM_xyz/`), which we co-register to the sensor
locations so spatial maps are honest about *where* on the slope each
finding sits.

The repository is the analysis pipeline plus the writeup, not the raw
data. The full ~12 GB dataset (per-logger METER ZL6 CSVs, `.xyz`
point-cloud scans, the DEM, and the OhmPi resistivity campaign) lives
outside the repo and is unzipped at the repo root so it lands at
`data/` (gitignored). The scripts load from there via
`config/settings.json`, whose `data_root` defaults to the repo-relative
`data/unpacked`.

## What the pipeline produces

Run order is the filename prefix:

**Event detection and per-event metrics**

| Script | Output |
|---|---|
| `00_detect_events_from_soil.py` | Rain events from 10 cm VWC rises — K-of-N consensus on dVWC/dt (94 events; validated against rain-gauge record for gauge-valid window pre-2025-06-22). |
| `01_data_quality.py` | Per-sensor overview, sources, and equilibration-window panel. |
| `02_spectrum.py` / `02b_spectrum_mne.py` | Welch PSD per sensor / depth / treatment (scipy + MNE). |
| `03_spectrogram.py` | Morlet, Mexican-hat, and Cmor wavelet TFR per sensor. |
| `04_event_response.py` | Time-domain response around a chosen rain event. |
| `05_rising_limb_metrics.py` | Per-event rise: ΔVWC, time-to-peak, mean dVWC/dt per event × sensor. |
| `06_wetting_front_lag.py` | 10 cm → 40 cm onset / peak lag per location. |

**Recession / drainage analysis** (all read or produce `plots/07_recession_fits.csv`)

| Script | Output |
|---|---|
| `07_recession_fits.py` | Exponential + power-law fits to each recession tail; source CSV for 07c–k. |
| `07c_recession_tau_by_slope.py` | τ distributions slope-paired (Top / Mid+Mound / Bottom), common y-axis. |
| `07d_mid_mound_overlay.py` | VWC time series Mound vs control Mid, both depths, with long-run means. |
| `07e_event_amplitude_40cm.py` | 40 cm event response rate, ΔVWC distribution, big-amplitude event count. |
| `07f_diurnal_dry_season.py` | Composite-day diurnal VWC + soil temp, Mound vs Mid, dry-season windows (24-h centered high-pass). |
| `07g_pet_dvwc_regression.py` | Daily PM-FAO PET vs centered ΔVWC per location — identifies SMS07 transpiration signature (β ≈ −0.6, R² = 0.30). |
| `07h_centered_vs_forward_diff.py` | Side-by-side check: centered vs forward first difference gives equivalent β. |
| `07i_hourly_pet_regression.py` | Hourly PM-FAO PET vs centered ΔVWC + composite-day stack (currently Bottom 1 only). |
| `07j_captured_water.py` | Per-event ΔVWC → mm-equivalent column (10 cm sensor → 0.25 m layer, 40 cm → 0.40 m layer); swale vs control diff and cumulative budget. |
| `07k_annualized_water_budget.py` | Annualises captured-water totals to mm/yr/m²; projects to litres at 10/50/200 m² scenarios. |

**PET (potential evapotranspiration)**

| Script | Output |
|---|---|
| `08_pet_hargreaves.py` | Daily Hargreaves-Samani PET — legacy fallback. |
| `08b_pet_diurnal_envelope.py` | Three-panel PET visualisation: full record, hourly disaggregation, composite-day envelope. |
| `08c_penman_monteith.py` | **Default PET.** Full FAO-56 PM ETo (measured T, P, ea; assumed u₂ = 2 m/s; Rs from Hargreaves). Outputs `plots/08c_pm_daily.csv`. |

**Spatial maps and DEM**

| Script | Output |
|---|---|
| `09_sensor_layout.py` | Plan-view map of the 8 sensor pairs with Widmer-thesis location labels (uses picked locations). |
| `10_per_location_vwc.py` | VWC time series, one panel per sensor along the slope, one figure per depth. |
| `11_per_location_tau.py` | Per-sensor median recession τ on a hillshaded plan-view map — **hero figure**. |
| `12_dem_views.py` | DEM 2-D (`tripcolor` + contours) and 3-D (PyVista oblique, 2× Z exaggeration). |
| `12b_dem_overlay_flipped_xy.py` | Sweeps all 8 XY transform variants over the DEM to identify the correct 180° registration. |
| `12d_sensors_over_dem2024.py` | `DEM_2024_07_25` overlay in raw survey frame rotated 180°; exports rotated DEM/sensor/electrode CSVs to `plots/`. |
| `13_xyz_inventory.py` | Streaming inventory of the raw `.xyz` LiDAR scans. |
| `14_xyz_aligned.py` | Per-scan aligned plan views after the rotation table. |
| `15_xyz_average_dense.py` | 5-scan averaged surface model (~1 mm per-bin std). |
| `16_pick_sensor_locations.py` | Interactive picker: DEM hillshade + draggable SMS markers; `s` saves to `plots/picked_sensor_locations.csv`. Used to hand-correct survey positions against terrain. |

**Diagnostics (non-numbered, one-off)**

| Script | What it does |
|---|---|
| `check_new_data_dump.py` | Diffs a new METER CSV portal export against the cache; read-only, prints headline counts. |
| `diagnose_jumps.py` | Per-sensor source-coloured overlays + numeric boundary report (bulk_ec jump diagnostic). |
| `sensor_mapping_widmer.py` | Cross-checks SMS01–16 metadata against Widmer (2024) Table 6. |

Plot outputs land in `plots/` (gitignored — regenerate from the
scripts). The CSV exports next to each plot are the structured form
of what the figure shows.

## Project layout

```
src/swale/        Loaders, configs, analysis helpers (importable as `swale`)
  config.py            Single source of truth for run-time settings + equilibration cutoff
  loader.py            Long-form dataframe of all sensor readings, cached as Parquet
  metadata.py          Parses the Metadata.xlsx → sensor + port mapping
  readers.py           CSV / XLSX readers for the METER ZL6 export format
  schema.py            Normalisers (sensor type, variable name, port label)
  preprocessing.py     Time-grid helpers (gap interpolation, regular reindexing)
  events.py            Soil-moisture-based rain-event detector
  sites.py             Sensor locations + Widmer-thesis labels (canonical frame)
  spatial_frame.py     +X=East, +Y=North, +Z=up — the canonical map orientation
  hillshade.py         Hillshade base from averaged LiDAR scans
  xyz_streaming.py     Memory-bounded streaming of raw .xyz point clouds
  xyz_align.py         Per-scan rotation table + cached histograms

scripts/          Numbered analysis scripts (run order = filename prefix)
tests/            pytest unit tests + a slow real-data smoke test
config/           settings.json, lgar_setup.json
notes/            Design notes (LGAR setup, recession-tail derivation)
data/             [gitignored] raw inputs; metadata XLSX is the only exception
plots/            [gitignored] regenerated by running the scripts
cache/            [gitignored] Parquet cache + xyz_histograms cache
```

## Spatial frame

All map-view plots in this project share **one** orientation:
**+X = East, +Y = North, +Z = up** (vertical). Sign multipliers (raw
to canonical) are set in `config/settings.json:spatial_frame`. Loaders
(`sites.load_sensor_pairs`, `spatial_frame.load_canonical_dem_mesh`,
the default XYZ rotation) apply the transform once at load time, so
every downstream plot draws natively without `ax.invert_*axis()`
tricks. See `src/swale/spatial_frame.py` for the full convention.

For this repository state, that canonical transform is a 180-degree
rotation implemented as `raw_x_sign = -1` and `raw_y_sign = -1`. The
new `12d_sensors_over_dem2024.py` diagnostic does not change the
project-wide setting; instead it starts from the original
`data/DEM/DEM_2024_07_25.txt` survey frame and writes a rotated bundle
to `plots/`:

- `12d_sensors_over_dem2024_rot180.png`
- `12d_dem2024_rot180_raster.xyz`
- `12d_sensor_locations_rot180.csv`
- `12d_electrode_locations_rot180.csv`

### Canonical surface model for ERT (2026-06-05)

For electrode/sensor **elevation**, the project uses the **24.05.30 terrestrial
scan** (`data/DEM_xyz/24.05.30_-_con_sw_and_for_11_59_00.xyz`), **not**
`DEM_2024_07_25` and **not** the per-electrode `Z_av`. The earlier "negate
`Z_av`" convention was wrong: against the measured surface the raw `Z_av` is
already up-positive (control high, swale low, in both the survey and the LiDAR),
and `Z_av` carries survey spikes (e.g. line-A electrode 3). Always obtain
topography through `ohmpi/scripts/scan_dem.py`:

- `scan_dem.world_to_scan(x, y)` maps survey canonical coords onto the scan
  (2-D similarity, **no reflection**, scale 1.0157, rotation −21.86°, fitted from
  the two soil-profile pits visible as square depressions in the scan).
- `scan_dem.elevation(x, y)` returns the scan-derived elevation; cached height
  grid at `ohmpi/cache/scan_dem_grid.npz`.

This registration must be applied in all future ERT processing. (One SMS sensor
still needs a small manual nudge; a full 3-D ICP refine is a later upgrade.)

## Setup

A conda env (the author uses miniforge) with an editable install pulls
every dependency from `pyproject.toml`:

```bash
conda create -y -n swale python=3.12
conda run -n swale pip install -e ".[dev]"
```

A plain venv works identically (`python3 -m venv .venv && .venv/bin/pip
install -e ".[dev]"`).

Unzip the dataset at the repo root so the data lands at `data/`.
`config/settings.json` already points at the in-repo tree:

```json
{
  "data": {
    "data_root": "data/unpacked",
    "metadata_xlsx": "data/Metadata.xlsx"
  }
}
```

Both paths are resolved relative to the repo root when not absolute
(see `src/swale/config.py`). `data_root` holds the per-logger export
folders (`data/unpacked/05511/`, `/19570/`, `/19574/`); point it at an
absolute path instead if you keep the data elsewhere.

The editable install puts `swale` on the path, so scripts run directly:

```bash
conda run -n swale python scripts/11_per_location_tau.py
```

## Tests

```bash
conda run -n swale pytest                  # unit tests, <1s
conda run -n swale pytest -m slow          # +real-data smoke (~20s)
```

The unit suite covers the metadata parser, the readers, the loader's
source-merge logic, and the rain-event detector.

## References

- Widmer, N. (2024). *Soil moisture and infiltration analysis of a
  swale system in Sadhana Forest.* M.Sc. thesis, ETH Zürich (cited
  throughout the analysis scripts and notes).
- LGAR-Py (Layered Green-Ampt with Redistribution) is referenced as
  the target physics model for the next-phase forward simulation;
  setup notes in `notes/lgar_design_choices.md`.

## Current state

See `CHANGELOG.md` for the dated session log and `TODO.md` for the
open follow-ups (event-level drill-down at the swale 40 cm Bottom-slope
sensors; the SMS 6,7 vs 8,9 layout question; rain-gauge inspection).
