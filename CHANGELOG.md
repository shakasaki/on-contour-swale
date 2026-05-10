# Changelog

All notable changes to the swale project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 2026-05-10 — infiltration analysis session

### Added
- `src/swale/events.py` — soil-moisture-based rain-event detector. Smoothed
  centered-difference `dVWC/dt` per 10 cm sensor, K-of-N consensus across
  sensors, gap coalescence, configurable via the `DetectorConfig` dataclass.
  Exposes `detect_events`, `align_to_grid`, `smoothed_derivative`, and
  `match_events` (precision/recall vs a reference event set).
- `tests/test_events.py` — 9 unit tests for the detector: derivative
  amplitude/NaN propagation, grid alignment, K-of-N consensus,
  coalescence, far-apart event separation, and the matching scorer.
  Full suite now 24 tests, ~56 s with the slow real-data smoke test.
- Numbered analysis scripts (run order = number; outputs share the prefix):
  - `scripts/00_detect_events_from_soil.py` — runs the detector across the
    full record, validates against `plots/rain_events.csv` for the gauge-
    valid window (start → 2025-06-22) with a multi-threshold precision/
    recall sweep, writes `plots/00_events_from_soil.csv` (94 events) and
    `plots/00_events_from_soil_validation.png` (rain trace + 10 cm VWC +
    onset rug). Detector hits 76 % overall precision and 86 % recall on
    gauge events ≥ 10 mm; missed events are dominated by sub-2 mm tips
    that don't move VWC.
  - `scripts/01_rising_limb_metrics.py` — per (event × sensor): baseline,
    peak, ΔVWC, time-to-peak, mean dVWC/dt during the rise. Output CSV
    + boxplot grid (`plots/01_rising_limb_metrics.{csv,png}`).
  - `scripts/03_wetting_front_lag.py` — 7 paired locations (4 swale +
    3 control). Onset-to-onset and peak-to-peak lag 10 cm → 40 cm, plus
    40 cm response-rate bar chart. Output CSV + 3-panel plot.
  - `scripts/04_recession_fits.py` — both `A·exp(-t/τ) + C` and
    `A·(t-t_peak)^(-α) + C` fitted with `scipy.curve_fit` per recession
    tail (peak → next event start − 2 h, capped at 7 d). Outputs:
    `04_recession_fits.csv`, `_distributions.png`, `_examples.png`
    (best-R² fit per depth × treatment), `_representative_events.png`
    (full event windows for 3 large clean events, ranked by 10 cm
    response magnitude with τ ∈ [5, 500] h and R² ≥ 0.7).

### Findings (informal, from this session)
- 10 cm: swale ΔVWC median 0.029 vs control 0.019 — swale wets *more*
  per event. Recession τ at 10 cm: swale 95 h vs control 58 h
  (~1.6× slower drying).
- 40 cm: swale and control respond to ~53 % vs 55 % of events with
  similar onset lag (~5–6 h). When the swale 40 cm does respond, ΔVWC
  is comparable to control (~0.013 m³/m³). But the recession τ is
  ~3261 h (swale) vs 73 h (control) — the swale 40 cm essentially
  doesn't drain on weekly timescales. This refines the prior reading
  that "water doesn't penetrate" — water *does* reach 40 cm in the
  swale at modest amplitude, but is then strongly buffered.
- The representative-events plot shows this contrast cleanly: control
  40 cm pumps up and drains within 1–2 days while swale 40 cm holds
  flat.

### Changed
- All session-1 plot outputs were renamed to share their producing
  script's number (`00_*`, `01_*`, `03_*`, `04_*`) so the run order is
  visible at a glance and outputs link unambiguously to scripts.

### Added
- `src/swale/preprocessing.py` — shared helpers (`regular_series`,
  `interpolate_short_gaps`, `longest_contiguous`, plus `GRID_SECONDS` /
  `SAMPLES_PER_DAY` constants) so all spectral / event scripts use the
  same gap-bridging and segment-selection logic.
- Time-frequency scripts (modular, with tunables at the top of each):
  - `scripts/spectrum.py` — Welch PSD via scipy. Two passes per run:
    7-day window for clean mid-band, full-record (~1 yr) periodogram for
    seasonal reach. Solid for swale, dashed for control.
  - `scripts/spectrum_mne.py` — same plot routed through
    `mne.time_frequency.psd_array_welch`. Numerically equivalent to
    scipy; kept for library consistency with the TFR pass.
  - `scripts/spectrogram.py` — Morlet wavelet TFR via MNE, plus
    pyWavelets backends `mexh` (Mexican Hat — sharper time, fuzzier
    frequency, the CWT analog of Haar for sharp transitions) and `cmor`.
    One figure per depth (`spectrogram_<depth>cm_<wavelet>.png`); rows =
    rain (top, log-y vlines) + one per sensor at that depth, swale rows
    titled blue, control titled red. In-axes labels on white bbox so
    titles stay legible regardless of figure scaling.
  - `scripts/event_response.py` — time-domain plot around a user-chosen
    rain event. Cumulative rain line on top; one row per depth with
    every sensor as a separate line (color = treatment, linestyle cycles
    within treatment). Defaults to the 2025-06-11 event.
- TFR cache layer at `cache/tfr/<sensor>_<wavelet>_<hash>.npz`. Hash
  covers wavelet, frequency grid, n_cycles, decim, cmor params, and
  the input vals bytes — so any metadata change that swaps a sensor's
  contiguous segment auto-invalidates. Cold runs ~1–2 min, warm ~12 s.
- `plots/rain_events.csv` — 84 detected rain events (≥ 1 mm total,
  ≤ 3-h quiet gaps absorbed within an event) with start/end/duration/
  total/peak columns.
- Dependencies in `pyproject.toml`: `scipy`, `matplotlib`, `seaborn`,
  `mne`, `pywavelets`. Project venv set up at `.venv/`. `.gitignore`
  added (covers `cache/`, `.venv/`, `__pycache__/`, etc.).

### Changed
- **Metadata schema**: two new columns (`tag`, `treatment`) inserted in
  the `Serials` sheet between `Location` and `Depth cm`. Parser
  (`src/swale/metadata.py`) updated to read tag/treatment at their new
  offsets and propagate `tag` through to the loader's enriched output.
  The Dataloggers subtable also shifted (Port 1 moved from column 6 to
  8); parser now discovers the Port-1 column from the header row so it
  stops breaking on column inserts. Without that fix SMS08, SMS09,
  SMS15, SMS16 silently dropped from the dataset.
- Treatment derivation prefers the explicit `treatment` column over
  the location-prefix derivation; falls back to derivation if missing
  or unrecognised. Location-prefix logic remains so 'Step??' (SMS10)
  and '?' (SMS23/SMS24) still surface as needing review.
- Control depth values now populated in metadata (SMS11/13/15 = 10 cm,
  SMS12/14/16 = 40 cm). Sensor counts at each analysis depth are now
  4 swale + 3 control at 10 cm; 5 swale (incl. SMS10 step) + 3 control
  at 40 cm. Cache regenerated.

### Known issues
- **Rain gauge silent from 2025-06-22 22:15 onward** (logger 19570).
  The logger keeps reporting at 5-min cadence — 62,713 rows of exact
  `0.0` through 2026-02-03, no nulls — so the data flow is healthy.
  Most likely cause: mechanical jam at the tipping bucket or
  disconnected ECRN-100 lead. Practical impact: any rain-driven analysis
  is bounded above by 2025-06-22 until the gauge is inspected on-site.
- SMS23 / SMS24 still have `Location='?'` and no treatment / depth.
  Excluded from analysis.

### Findings (informal, from this session)
- 10 cm soil moisture responds sharply to rain in both treatments;
  swale runs slightly higher and the recession shape is similar.
- 40 cm shows a striking treatment difference: swale 40 cm sits at
  ~0.05–0.10 m³/m³ (water doesn't penetrate the swale architecture to
  this depth within a 25-day window post-event), while control 40 cm
  sits at ~0.30–0.45. Worth following up.
- Spectrograms reveal the diurnal-cycle band at 24 h modulating in
  amplitude across wet/dry seasons; rain events show as wavelet cones.
  Treatment difference at the spectrogram level is not visually obvious
  — event-window time-domain analysis is more discriminating for this.

## 2026-05-08

### Added
- Project skeleton: `pyproject.toml` (polars, fastexcel, openpyxl, pytest),
  `src/swale/` package, `tests/` with synthetic-fixture helpers in
  `tests/conftest.py`.
- `src/swale/schema.py` — single source of truth for the textual quirks of
  METER ZL6 exports: `SENSOR_TYPE_MAP`, `VARIABLE_MAP`, `LOGGER_INFO`,
  `KEPT_SENSOR_TYPES`, plus normalizers `parse_port_label`,
  `normalize_sensor_type`, `normalize_variable`, `logger_serial_from_name`.
- `src/swale/metadata.py` — `parse_metadata(metadata_xlsx)` that returns a
  long sensors table and a (logger_serial, port) → sensor_id port-mapping
  table. Handles the awkward stacked layout of the `Serials` sheet, drops
  Forest sensors and the Forest logger 05533, normalises ID formatting
  (`SMS 16` → `SMS16`), and synthesises rows for the logger-internal
  Battery / Barometer channels and the ATMOS 14 / ECRN-100 sensors on
  logger 19570.
- `src/swale/readers.py` — `read_logger_csv` and `read_logger_xlsx`. Both
  return the same long DataFrame schema with columns `timestamp, port,
  sensor_type, variable, value, source_format, source_file, config_label`.
  Handles the 3-row CSV/XLSX header, multiple `Processed Data Config N`
  sheets per Excel file, ASCII vs Unicode unit strings, and unsorted /
  blank rows.
- `src/swale/loader.py` — `load_swale_dataset(data_root, metadata_xlsx,
  cache_dir, refresh, grid, on_conflict)`. Discovers per-logger CSVs and
  Excel snapshots, runs the readers, drops implausible-year timestamps,
  detects and warns on cross-source value disagreements (with combined
  abs+rel tolerance), dedups with XLSX preferred over CSV, joins
  metadata, optionally reindexes onto a regular time grid, and caches as
  Parquet partitioned by logger.
- Tests: 14 unit tests (`tests/test_metadata.py`, `tests/test_readers.py`,
  `tests/test_loader.py`) + 1 slow real-data smoke test
  (`test_loader_real_dataset_smoke`) gated behind `@pytest.mark.slow`.
  All passing; full suite under 1 second; smoke against
  `/home/alexis/DATA/swale` runs in ~75 seconds.
- Plotting scripts: `scripts/make_plots.py` (weather panel for logger
  19570 + soil moisture/temp/EC by depth × treatment grid),
  `scripts/diagnose_jumps.py` (per-sensor source-coloured overlays plus a
  numeric boundary report). Outputs land in `plots/`.
- One-off equilibration plot: `plots/first_two_weeks.png` showing the
  first 14 days per TEROS 12 sensor since its first valid reading;
  reveals 1–4 day instrument settling and supports a 1-week startup cut.

### Changed
- Source priority: XLSX preferred over CSV on overlapping rows (CSV
  exports are display-rounded to 3 decimals; XLSX carries the
  full-precision calibrated values).
- Conflict tolerance loosened to `isclose(atol=1e-3, rtol=1e-3)` so the
  CSV's 3-decimal display rounding is no longer flagged as disagreement.
- Implausible timestamps (year < 2018 or ≥ 2030) are dropped with a
  warning — caught 14 such rows from a single Excel snapshot whose
  logger-clock had glitched into 2035.

### Known issues
- `bulk_ec` is aliased from XLSX `Bulk EC` and CSV `Saturation Extract
  EC`, which are physically different quantities. This produces a
  visible step jump (1.7–3.3 mS/cm) at the XLSX → CSV source switch
  around 2025-02-04 for sensors on loggers 05511 and 19570. Sensors on
  19574 don't show the jump. See `memory/bulk_ec_source_artifact.md`
  and `plots/diag_bulk_ec.png`. Fix deferred pending the user's check
  for older XLSX snapshots.
- Control sensors (SMS11–SMS16) and SMS10 have no depth recorded in the
  metadata spreadsheet, so they cannot currently be compared
  depth-for-depth against swale sensors. Loader emits a warning at
  parse time.
