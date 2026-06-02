# TODO

## 2026-06-02 — OhmPi geometry + R table
- [x] **Per-survey R table for lines A–D** (`ohmpi/scripts/build_r_table.py`) — sign-flip estimator `R = Σ(V·pol)/Σ(I·pol)` on every A–D quad, streamed per-survey; cached to `ohmpi/cache/r_table.parquet` (74,146 rows + reciprocal R/err, `keep`/`drop_day` flags, QC medians). Per-quad cut: median |vmn|≥1 mV AND recip≤5% → 118/296 quads kept. Validated: test-circuit quad 99.3 Ω, matches instrument `r` to 3–4 sig figs everywhere.
- [x] **Geometric factor + apparent resistivity** (`ohmpi/scripts/geometry.py`) — quad a/b/m/n confirmed = OhmPi channel numbers; real coords from `merged_electrode_table.xlsx` (NOT the idealised `electrode_geometry.csv`). 3D half-space K attached to the R table as `K`, `rho_a`. dipdip and wenner agree: ρ_a ≈ 5.6 Ω·m. Negative dipdip R × negative dipdip K = positive ρ_a (resolved the sign puzzle).
- [issue] **Electrode coordinate frame** — (1) Z sign in `merged_electrode_table.xlsx` is inverted (negating it puts B upslope/highest, E downslope, A descending with electrode number — matches the field); (2) electrode XY not registered to the DEM (best-fit transpose+flip only ~0.2 m RMS). **User fixing upstream and pushing corrected coordinates.** K/ρ_a unaffected (distance-invariant); only DEM-map placement waits on this.
- [ ] **Find a moderate-SP-drift quad for the static/dynamic/linear SP writeup** — line E quads are too far gone (railing at ±7500 mV) to illustrate the *rescuable* case. Need a quad where SP ramps smoothly during the measurement but the signal is still recoverable, to demonstrate that a linear-drift SP fit beats both static (constant) and sign-flip when SP isn't constant. Then document which model fits which dataset.
- [ ] **Build the Bokeh waveform browser** for on-demand quad inspection (dropdown over quads → waveform across all surveys), the scalable alternative to static per-survey plots. Base on `ohmpi/scripts/guillaume_plot_data.py`.
- [ ] **Blacklist bad survey-days** — vertical red stripes in the dipdip heatmap = whole-survey failures across all quads (battery/rain/connection). Compute per-day pass fraction and drop the bad dates globally.
- [issue] **Line E central electrodes 51–57 are a hardware fault** — electrode #54 at ~5 kΩ contact (25× normal), quads through the zone rail at ±7500 mV, broken since campaign start. Drop quads touching 51–57; salvage the end quads (e.g. `56_59_57_58`). Physical fix needed on site (likely a damaged central cable section / corroded electrode 54).

## 2026-05-26 — open
- [ ] **Extend hourly PET regression to more sensor pairs** — `07i_hourly_pet_regression.py` currently covers Bottom 1 only. Run for Mid/Mound, Top, and Bot 2 to see whether any other position shows a clean midday-drawdown signature in the composite-day stack. If only Bot 1 has it, the "trees at the foot of the slope" interpretation tightens.
- [ ] **Update slide deck to use the display-name convention consistently** — `notes/presentation_slides.md` still has a mix of `SMSnn` and `sw_/cn_` labels in the prose tables. Sweep through and unify.
- [ ] **Hardware wishlist for PM-FAO PET** — the Penman-Monteith implementation in `08c_penman_monteith.py` assumes `u₂ = 2 m/s` (FAO default) and estimates `Rs` from Hargreaves `K_rs · √ΔT · Ra` because we have no on-site anemometer or pyranometer. A cup anemometer (~$100) is the highest-impact upgrade — would remove the wind assumption. Pyranometer next, for measured `Rs`. Re-run PM-FAO and the SMS07 regression with measurements once installed.

## 2026-05-14 — open

- [ ] **40 cm drill-down, event-level phase**. Per-location τ map now shows the slow-drainage at swale 40 cm concentrates at Bottom slope 1+2 (SMS07/09), not at the Mound or Step. Next: event-by-event drilldown — compare a handful of large events at SMS07/09 vs SMS05/10 vs control SMS12/14/16 to see which events drive the per-sensor τ spread. Curated subset from `plots/00_events_from_soil.csv`.
- [ ] **SMS 6,7 vs SMS 8,9 position question in `SMS_locations.csv`** (user-owned). The Widmer-location vs surveyed-XY mapping for Bottom slope 1 vs 2 needs a source-data check; user said "I need to dig into the data to fix this".
- [ ] **SMS02 (Top slope swale, 40 cm) has only 1 good recession fit.** The Top slope 40 cm rarely responds enough to fit clean recessions. Either lower R² threshold for this sensor, or accept the data-poor caveat in any per-location summary.
- [ ] **Logger 19574 soil_temp XLSX anomaly** (SMS06 + SMS08): xlsx-side cache values diverge from CSV by 1.7–9 °C over 2024-11-29 → 2025-05-02 with v_cache stuck at 25.5 °C. Investigate the bad XLSX snapshot, decide whether to deprefer it or rewrite the dedup rule on that window.
- [ ] **Cache typing anomaly on ATMOS14_19570**: a subset of rows are stored with `sensor_type = 'TEROS12'` for moisture/soil_temp/bulk_ec. Trace through the port-5 history on logger 19570 and fix in the reader or loader.
- [ ] Optional follow-up on time-frequency: swale-minus-control difference TFRs to highlight where the treatments diverge in frequency-time.
- [ ] Optional: discrete Haar (DWT) decomposition for sharp-transition characterisation.

## Done in the 2026-05-14 spatial drill-down session

- [x] **Sensor layout map** with Widmer-location labels + uncertainty ellipse (`scripts/09_sensor_layout.py`, `plots/09_sensor_layout.png`).
- [x] **Per-location VWC time series** (`scripts/10_per_location_vwc.py`, `plots/10_per_location_vwc_{10,40}cm.png`).
- [x] **Per-location recession τ map** with hillshade base + DEM bbox overlay (`scripts/11_per_location_tau.py`, `plots/11_per_location_tau_map.png`). Reveals that the slow drainage at swale 40 cm concentrates at Bottom slope 1+2 (SMS07 τ=103 h, SMS09 τ=132 h), not uniformly across the swale.
- [x] **DEM 2-D + 3-D views** (`scripts/12_dem_views.py`). Top-down `tripcolor` with 0.10 m contours; PyVista oblique with 2× Z exaggeration.
- [x] **XYZ scan inventory** (`scripts/13_xyz_inventory.py`) — memory-bounded streaming summary of all 22 raw scans; trims `data/DEM_xyz/` from 22 to 17 files (5 dense `con_sw_and_for_*` + 12 task-specific scans) after confirming the 5 dense scans are independent measurements of the same area with sub-cm registration.
- [x] **XYZ rotation table + aligned plots** (`scripts/14_xyz_aligned.py`) + **5-scan average** (`scripts/15_xyz_average_dense.py`).
- [x] **DEM↔sensor coordinate registration → canonical frame.** Spec'd in `config/settings.json:spatial_frame` and implemented in `src/swale/spatial_frame.py`. **+X = East, +Y = North, +Z = up.** Loaders (sites.py, DEM mesh helper, XYZ rotation default) apply the raw→canonical transform at load time, so every map plot draws natively with no `invert_*axis()` tricks.
- [x] **Canonical-frame hillshade base layer** from the averaged 5 dense scans, cropped to the DEM mesh extent (`src/swale/hillshade.py`). Layered under the τ map.

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
