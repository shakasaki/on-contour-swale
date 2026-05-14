# TODO

## 2026-05-14

- [ ] **40 cm treatment difference drill-down — spatial phase** (top priority, in progress). Now that `data/SMS_locations.csv` gives metric (X,Y,Z) per sensor pair, plot the 5 swale + 3 control pairs in their actual layout and re-look at the τ ≈ 3261 h swale-40 cm signature per-location instead of pooled. Hypothesise mechanism (which location is buffering: mound? trench? step?) and test against more events.
- [ ] **DEM↔sensor coordinate registration**. `data/DEM/DEM_2024_07_25.{txt,las,shp,vtk}` is in a different local frame from `SMS_locations.csv` (DEM X ≈ 10–12, sensors X ≈ −12 to +6). Need an alignment step (rigid rotation+translation, or pick common landmarks) before overlaying sensors on hillshade.
- [ ] Event-based drydown analysis on a curated subset of events from `plots/00_events_from_soil.csv`.
- [ ] **Logger 19574 soil_temp XLSX anomaly** (SMS06 + SMS08): xlsx-side cache values diverge from CSV by 1.7–9 °C over 2024-11-29 → 2025-05-02 with v_cache stuck at 25.5 °C. Investigate the bad XLSX snapshot, decide whether to deprefer it or rewrite the dedup rule on that window.
- [ ] **Cache typing anomaly on ATMOS14_19570**: a subset of rows are stored with `sensor_type = 'TEROS12'` for moisture/soil_temp/bulk_ec. Trace through the port-5 history on logger 19570 and fix in the reader or loader.
- [ ] Optional follow-up on time-frequency: swale-minus-control difference TFRs to highlight where the treatments diverge in frequency-time.
- [ ] Optional: discrete Haar (DWT) decomposition for sharp-transition characterisation.

## Backlog (carried over)

- [ ] **Rain gauge inspection** (logger 19570). Silent from 2025-06-22 22:15 onward; data flow healthy, values pegged at 0.0. Likely mechanical jam or disconnected lead. Until repaired, all rain-driven analysis is bounded above by 2025-06-22.
- [ ] Look for older XLSX snapshots that extend XLSX coverage of loggers 05511 and 19570 past Feb 2025 — if found, ingest them and re-evaluate whether the bulk_ec / saturation-extract-EC aliasing is still acceptable.
- [ ] Re-ingest the post-2026-02-04 portion of the new CSV dump into the cache (extends record by ~3 months). `check_new_data_dump.py` confirms moisture agreement is rock solid.

## Done in 2026-05-11 – 2026-05-14 session

- [x] Inspected the new METER CSV dump in `data/All-z6-*.zip`; wrote `scripts/check_new_data_dump.py` to diff vs cache and dropped headline numbers in CHANGELOG.
- [x] Added `config/settings.json` + `swale.config` helper. 14 d global equilibration cutoff with per-sensor overrides.
- [x] Auxiliary `plots/01_equilibration.png` per-sensor first-21-days panel grid added to `01_data_quality.py`.
- [x] Renumbered scripts so run order = filename prefix; renamed plot outputs to match.
- [x] SMS10 disposition: kept as the 5th swale-40 cm sensor (user decision).
- [x] Verified SMS17–22 don't exist; SMS23/24 already excluded via null treatment.
- [x] Daily Hargreaves-Samani PET (`scripts/08_pet_hargreaves.py`).
- [x] Widmer Table 6 cross-check (`scripts/sensor_mapping_widmer.py`).
- [x] LGAR-Py reference setup notes (`notes/lgar_design_choices.md`, `config/lgar_setup.json`).
- [x] Recession-tail derivation note (`notes/recession_tail_richards.{tex,pdf}`).

## Issues

- [issue] `bulk_ec` step jump of 1.7–3.3 mS/cm at ~2025-02-04 on loggers 05511 + 19570 is a source-switch artifact (Bulk EC vs Saturation Extract EC aliased). Diagnostic in `plots/diag_bulk_ec.png` and `plots/boundary_report.csv`. Fix deferred — see `memory/bulk_ec_source_artifact.md`.
- [issue] Rain gauge on logger 19570 reports continuous 0 mm from 2025-07 onward through 2026-02 (~8 months) despite ~8928 rows/month being logged at 5-min cadence. 2024-08 had 323 mm; 2025-08 has 0 mm. Almost certainly a physical fault (clogged tipping bucket, stuck mechanism, or detached lead). Action: have the gauge inspected on-site; meanwhile any analysis that relies on rain forcing is restricted to ≤ 2025-06.

## Done in this session

- [x] Time-frequency phase started: scipy & MNE Welch PSD, Morlet/mexh/cmor TFR, multi-sensor spectrogram per depth, TFR caching, event-window time-domain plot.
- [x] Control depths populated in metadata; cache refreshed; metadata parser updated for new `tag` and `treatment` columns and the Dataloggers subtable column shift.
- [x] Detected and tabulated 84 rain events (`plots/rain_events.csv`).
- [x] Confirmed rain-gauge failure post 2025-06-22 (documented in Issues).

## Issues

- [issue] `bulk_ec` step jump of 1.7–3.3 mS/cm at ~2025-02-04 on loggers 05511 + 19570 is a source-switch artifact (Bulk EC vs Saturation Extract EC aliased). Diagnostic in `plots/diag_bulk_ec.png` and `plots/boundary_report.csv`. Fix deferred — see `memory/bulk_ec_source_artifact.md`.
- [issue] Rain gauge on logger 19570 reports continuous 0 mm from 2025-07 onward through 2026-02 (~8 months) despite ~8928 rows/month being logged at 5-min cadence. 2024-08 had 323 mm; 2025-08 has 0 mm. Almost certainly a physical fault (clogged tipping bucket, stuck mechanism, or detached lead). Action: have the gauge inspected on-site; meanwhile any analysis that relies on rain forcing is restricted to ≤ 2025-06.
