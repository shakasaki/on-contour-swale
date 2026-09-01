# Changelog

All notable changes to the swale project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 2026-09-01 — ZENTRA Cloud v5 wired into the loader; record extended to Aug 2026

### Added
- **`src/swale/readers.py::read_logger_parquet`**: reads a
  `data/zentracloud/<serial>.parquet` dump (from `fetch_zentracloud.py`)
  into the same long format as `read_logger_csv`. v5 `datetime` (UTC) is
  converted to naive field-local time via `Asia/Kolkata` (IST, +5:30, no
  DST — Sadhana Forest, Auroville; offset pinned by r=1.000 soil-temp
  cross-correlation vs the CSV). Unmapped v5 measurements (`Raw VWC`,
  `Pore Water EC`, `Dew Point`, `Signal`) are dropped.
- **`error_code`** column added to the loader's long schema (`Int32`, null
  for CSV/XLSX rows, the METER quality code for v5 rows). Carried through
  dedup and reindex; left null on synthetic grid rows.
- **`schema.py`**: `V5_MEASUREMENT_MAP`, `V5_SENSOR_TYPE_MAP`,
  `normalize_v5_measurement`, `normalize_v5_sensor_type`.
- **`sat_extract_ec`** as a distinct variable (see Changed / EC split).
- **`scripts/zentracloud_health_report.py`** + **`notes/field_sensor_faults.md`**:
  classifies every logger port by its `error_code` history and writes a
  list-format report of which datalogger + sensor is failing and since
  when. Full v5 history: `z6-19574` SMS09/`sw_b2_40` dead since 2026-03-28,
  SMS08/`sw_b2_10` degrading since 2025-01-24, SMS06/`sw_b1_10` an episodic
  2025/2026 fault (recovered).
- **`scripts/14_all_data_by_6mo.py`**: full-record walk-through — every
  variable in consecutive 6-month windows from the first reading, one
  figure per data-type group (soil / weather / housekeeping) per window;
  hourly-mean line + hourly min–max shaded band, flagged readings nulled,
  no equilibration cutoff. 15 figures (`plots/allrange_*.png`).

### Changed
- **`src/swale/loader.py`**: `load_swale_dataset` gains a `zentracloud_dir`
  arg (`"auto"` → `<data_root>/../zentracloud`, `None` to skip); v5 parquets
  are discovered and read alongside CSV/XLSX. `_SOURCE_PRIORITY` is now
  `{xlsx: 0, zentracloud: 1, csv: 2}` — v5 is full precision and current, so
  it wins over the display-rounded CSV in the overlap; CSV now only fills
  history predating each logger's v5 record (~24k rows survive dedup). The
  loaded dataset spans 2024-05-25 → 2026-08-29 (was → 2026-05-11), 17.1M
  rows.
- **EC split** (resolves the long-standing alias): the CSV's single
  "Saturation Extract EC" column and v5 "Saturation Extract EC" now map to
  `sat_extract_ec` (the continuous 2024→now series, i.e. the old `bulk_ec`);
  v5 "Bulk EC" maps to `bulk_ec` (v5-era only). Downstream renamed
  `bulk_ec` → `sat_extract_ec` in `scripts/01_data_quality.py`,
  `scripts/diagnose_jumps.py`, `config/settings.json` `equilibration.variables`
  and its `src/swale/config.py` default.
- **Full v5 history fetched** (`fetch_zentracloud.py --start 2024-05-01`):
  ~7.2–9.1M readings/logger to `data/zentracloud/*.parquet`.

### Fixed
- **`scripts/05_rising_limb_metrics.py`**: `measure_event` returns a Python
  `datetime` / `None` for `peak_time` instead of `np.datetime64("NaT")` —
  `pl.from_dicts` can't mix `NaT` with the `None` yielded when a sensor has
  no post-event data (now reachable with the longer record).

### Removed
- **`scripts/fetch_zentracloud_legacy.py`**: the v3/v4 REST path is
  unreachable now the account is on ZENTRA Cloud 2.0.

### Known issues
- `scripts/11_per_location_tau.py` is blocked on absent
  `data/DEM_xyz/24.05.30_-_con_sw_and_for_*.xyz` dense scans (pre-existing,
  hillshade rendering only — the τ computation is unaffected).
- `notes/figures_index.md` text still references the old 2026-05 end date
  for the pre-existing figures.
- Scripts 02 / 02b / 03 / 09 / 12* not yet re-run against the extended
  record.

## 2026-08-26 — Desktop memory-sync fix, SMS line transects, ZentraCloud fetch scripts

### Added
- **`scripts/13_sms_line_transects.py`**: elevation transects of SMS sensor
  pairs (swale vs control) along each treatment's along-slope principal axis,
  sampled from the `DEM_2024_07_25` point cloud; plus a plan-view companion
  overlaying both transect axes and electrode Line A as a sanity check. Run
  and verified — output matches expected swale mound/step/bottom-slope
  topography vs the flatter control profile.
- **`scripts/fetch_zentracloud.py`**: pulls raw readings for the three ZL6
  loggers (05511/19570/19574) from the ZENTRA Cloud **v5** API (new
  `zentracloud` PyPI SDK, `X-API-Key` auth) to `data/zentracloud/*.parquet`.
  Blocked until the account is migrated off the legacy platform.
- **`scripts/fetch_zentracloud_legacy.py`**: same, against the **legacy**
  v3/v4 REST API (`Authorization: Token`, `/api/v4/get_readings/`) that the
  account currently uses. Built from documentation only (no working
  credentials yet to verify against) — pagination stop-condition and
  response envelope need confirming against a real response once the new
  account is live.
- `pyproject.toml`: added `zentracloud` and `requests` dependencies for the
  two fetch scripts above.

### Fixed
- **Cross-machine Claude memory sync for this repo (desktop)**: this
  machine's session launches from `/mnt/data/git/on-contour-swale`, which
  hashes to a different Claude project dir than `~/git/on-contour-swale`
  (same repo, bind-mounted) — `dotsync/repos/on-contour-swale-claude.yaml`
  had no `desktop` path override, so this machine's real memory dir was
  never covered by sync. Added the override and reapplied via `stsync`.
  Fixing it hit a near-miss: restarting Syncthing to clear a "folder marker
  missing" error triggered a rescan of the still-empty new folder, which
  broadcast a delete-all to the ashakas laptop and wiped its copy. Recovered
  by repopulating the new folder from the intact copy before
  unpausing/rescanning; ashakas re-pulled to 100%. Full incident and the
  reusable "populate before scan" rule are in memory
  (`on-contour-swale-memory-sync.md`, `feedback_syncthing_populate_before_scan.md`).

## 2026-06-10 — Reciprocal-error weighting, difference imaging, convergence, MP4

### Added
- **Reciprocal-error weighting**: `write_protocols` now writes the ProtocolDC
  "DC 2D + err" 7th column (`|R|·recip_err_pct/100`, floored at `ERR_FLOOR_PCT`
  = 1 %) and `run_inversion` sets `k.err=True`, so R2 weights each datum by its
  measured reciprocal error instead of the default homogeneous model. Initial
  misfit becomes honest (~10×) and inversions converge to RMS≈1.
- **Difference imaging**: time-lapse runs call `k.postProcTl()` and the render
  **appends** a Δρ(%)-vs-reference panel (bwr, 0-centred, ±95th-pct scale) below
  the resistivity section. Individual mode unchanged.
- **Convergence plots**: `survey_rms` parses `invdir/R2.out` for the final RMS
  per survey; `plot_convergence` saves `convergence_<line>_<mode>.png` (RMS vs
  date, target=1). Median RMS A 1.04 / B 1.00 / C 1.00 / D 1.32.
- **MP4 output**: `write_mp4` (imageio-ffmpeg) replaces the fragile relative-path
  HTML scrubber for time-lapse — single seekable file. New dep: `imageio-ffmpeg`.

## 2026-06-09 — Inversion topography finalized + scrubbable time-lapse output

### Added
- `ohmpi/scripts/diag_elec_z_vs_dem.py` — planview check: electrodes coloured by
  surveyed `Z_av` on the same colormap as the 24.05.30 scan DEM (datum-matched),
  with per-line residual summary. Exposed that lines sit at different vertical
  offsets (B ~−0.6 m, E ~+0.4 m), which is why pooled `corr(Z_av, DEM)` is
  negative while per-line correlation is +0.8..1.0.
- Self-contained HTML scrubber for time-lapse output (`line_<L>_timelapse.html`):
  frame slider, ←/→ stepping, play/pause — replaces the non-seekable GIF.

### Changed
- `scan_dem.py` — sampling is now **bilinear on a NaN-aware Gaussian low-pass**
  of the height grid (`SMOOTH_SIGMA_BINS=3` ≈ 15 cm), replacing nearest-5-cm-bin
  lookup. Removes the jagged surface that made electrodes appear off the profile.
- `resipy_invert.build_profile` — per-line inversion topography (decided with
  Alexis): **A** drops the mound electrode (channel 6) to the line interpolated
  between channels 5↔7 (electrodes predate the mound); **C/D** use a straight-line
  fit (5/8 cm span, negligible); **B** keeps the smoothed DEM.
- Re-ran all 8 inversions (A–D × individual/timelapse) with this topography.

## 2026-06-05 — ResIPy time-lapse ERT inversion + scan-DEM registration

### Added
- `ohmpi/scripts/resipy_invert.py` — 2-D time-lapse ERT inversion of lines A–D
  with ResIPy 3.6.6 / R2 (via wine). Builds per-line profiles from surveyed
  electrode positions (SVD principal-axis projection), writes ProtocolDC files of
  sign-flip transfer resistance, and inverts in two schemes: `individual`
  (per-survey, `reg_mode 0`) and `timelapse` (background-constrained,
  `reg_mode 1`, first survey = reference). Renders 3-row frames (VWC 10 cm /
  40 cm / inverted section) + per-line GIFs under `ohmpi/outputs/inversion/`.
  Workarounds: monkeypatch `Survey.computeReciprocalC = computeReciprocalP`
  (cython read-only crash under numpy 1.26), explicit mesh `fmd=3.0`, electrodes
  set after survey import, serial inversion (parallel wine races on `R2.out`).
- `ohmpi/scripts/scan_dem.py` — canonical surface model. Uses the **24.05.30
  terrestrial scan** as the DEM and registers survey coords onto it with a 2-D
  similarity (no reflection, scale 1.0157, rotation −21.86°) fitted from the two
  soil-profile pits. `world_to_scan()`, `elevation()`, cached height grid
  `ohmpi/cache/scan_dem_grid.npz`.
- `ohmpi/scripts/diag_dem_elevation_check.py`, `diag_line_profiles.py`,
  `scan_line_transects.py` — diagnostics that established the topography sign was
  inverted (`-Z_av` anti-correlates with the LiDAR; raw `Z_av` is up-positive)
  and that line-A electrode 3 had a bad survey Z spike.

### Changed
- `resipy_invert.py:build_profile` now sources elevation from `scan_dem.elevation`
  instead of `-Z_av`. **Provisional** — see TODO: electrodes predate the mound,
  so their Z likely comes from Widmer's pre-mound survey, not the later scan.
- `README.md` — new "Canonical surface model for ERT" section documenting the
  scan-DEM choice and the registration transform.

## 2026-06-04 — OhmPi cache rebuild tooling + Wenner ρ_a time series vs VWC

### Added
- `ohmpi/scripts/build_all.py` — one-shot cache builder. Runs `build_r_table.py`
  then `build_waveform_cache.py`, skipping any cache already present (`--force`
  to rebuild). Fixes the blank-screen `bokeh serve` on a fresh checkout, where
  the gitignored `ohmpi/cache/` (r_table + 920 MB waveform set) is absent and
  `ohmpi_browser.py` dies at module load with
  `FileNotFoundError: r_table.parquet`.
- `ohmpi/README.md` — documents the gitignored-cache gotcha, `build_all.py`, the
  cache table, and how to run the Bokeh browser.
- `ohmpi/scripts/plot_wenner_timeseries.py` — weekly violin distribution of
  Wenner apparent resistivity per line A–D over the campaign (kept earth quads,
  shared 2–12 Ω·m axis), with each line's nearest 40 cm VWC on the top panel.
  Output `ohmpi/plots/wenner_rho_timeseries.png`.
- `ohmpi/scripts/plot_wenner_daily.py` — daily median ρ_a + inter-quartile band
  per line (245 days, 12–21 kept quads/line/day) with the line's nearest 40 cm
  VWC on a twin axis. Shows the inverse ρ_a–VWC coupling (ρ_a steps up at the
  August VWC minimum). Output `ohmpi/plots/wenner_rho_daily.png`.

### Changed
- Line→VWC sensor pairing resolved spatially (nearest 40 cm station per line
  from electrode↔sensor coords in the shared rot180 frame): A=SMS05 Mound,
  B=SMS02 Top, C=SMS10 Step, D=SMS05 Mound. Confirms the existing
  `animate_rho_a.py` hardcode was spatially consistent (A & D both nearest the
  Mound station, not a copy-paste error).

## 2026-06-02 — OhmPi R table, geometric factor, coordinate fix, ρ_a animation

### Added
- `ohmpi/scripts/build_r_table.py` — per-(survey,quad) sign-flip resistance
  table for lines A–D. Streams all ~2000 A–D `_fw.zip`s, applies
  `R = Σ(V·pol)/Σ(I·pol)` per quad, attaches reciprocal R, reciprocal error,
  per-quad QC flag (`keep`: median |vmn|≥1 mV AND recip≤5%), `drop_day` flag,
  K and `rho_a`. Cached to `ohmpi/cache/r_table.parquet` (74,146 rows).
  `ohmpi/cache/quad_qc.parquet` (118/296 quads kept). Validated: test-circuit
  quad 99.3 Ω; sign-flip R matches instrument `r` to 3–4 sig figs; dipdip and
  wenner agree at ρ_a ≈ 5.6 Ω·m campaign-wide.
- `ohmpi/scripts/geometry.py` — OhmPi channel→coordinate loader and 3D
  half-space geometric factor `K = 2π/[(1/r_AM−1/r_BM)−(1/r_AN−1/r_BN)]`.
  Confirmed: quad a/b/m/n = OhmPi channel numbers (not sequential 1–60 survey
  numbers). Real coords from `merged_electrode_table.xlsx`. K sign resolves
  the negative dipdip R: K<0 for co-linear dipdip, so K·R>0 throughout.
- `ohmpi/scripts/plot_geometry.py` — electrode layout plan view over DEM
  hillshade + elevation panel per line. Applies 180° rotation (x,y)→(−x,−y)
  to match canonical frame; negates Z_av for correct height order (B
  upslope/highest, E downslope).
- `ohmpi/scripts/animate_rho_a.py` — animated GIF of ρ_a pseudosection per
  line (A–D), one frame per survey day (~250 frames, 8 fps). Three panels:
  daily rain (gauge-fault greyed post-2025-06-22), VWC 40 cm for the closest
  SMS pair, and ρ_a scatter at (along-line position via PCA, pseudo-depth =
  half AB↔MN separation). Both dipdip (circles) and wenner (triangles) shown.
  Outputs to `ohmpi/plots/animations/rho_a_line_{A,B,C,D}.gif`.
- `scripts/12b_dem_overlay_flipped_xy.py` (user) — sweeps all 8 XY
  transform variants over the DEM to identify the correct registration.
- `scripts/12d_sensors_over_dem2024.py` (user) — applies the correct 180°
  rotation, exports `plots/12d_electrode_locations_rot180.csv`,
  `12d_sensor_locations_rot180.csv`, `12d_dem2024_rot180_raster.xyz`.

### Changed
- `pyproject.toml` — added `numpy>=1.26`, `pandas>=2.0`, `bokeh>=3.4` (were
  used directly but only transitive dependencies).
- `config/settings.json` — `data_root` changed from stale absolute
  `/home/alexis/DATA/sadhana/swale` to repo-relative `data/unpacked`.
- `src/swale/config.py` — `data_root` now resolved relative to repo root
  when not absolute (mirrors existing `metadata_xlsx` handling).
- `tests/test_loader.py`, `tests/test_metadata.py` — slow smoke tests
  rewired from stale `/home/alexis/...` paths to `load_settings()` so they
  actually run against the real in-repo data.
- `README.md` — updated Setup/Tests sections for conda env (`swale`), in-repo
  data tree, ~20 s slow-test timing.

### Fixed
- Electrode coordinate frame: raw X_av/Y_av in `merged_electrode_table.xlsx`
  require 180° rotation to match the DEM. `plot_geometry.py` and
  `animate_rho_a.py` now apply this. Also identified Z_av is stored inverted
  (fix pending in source table); `plot_geometry.py` negates Z for display.
- `compute_k.py` / `electrode_geometry.csv` identified as wrong for this
  dataset: sequential 1–60 numbering with 1 m flat grid does not match the
  real OhmPi channel numbers or surveyed positions. `geometry.py` uses the
  correct source.

## 2026-05-29 — OhmPi resistivity: fast loader, QC triage, test-circuit validation, line E diagnosis

### Added
- `ohmpi/scripts/ohmpi_loader.py` — polars loading layer for the OhmPi
  campaign (data at repo-root `data/ohmpi/`, 2496 surveys, 2025-04-08 →
  2026-01-22). `build_survey_index()` (one row/survey), `build_summary_table()`
  (concat all instrument `_results.csv` → ~92k survey×quad rows, with
  reciprocal error from pairing `a_b_m_n` with `m_n_a_b`), `load_waveforms()`
  (stream `_fw.zip`s, filter to chosen quads, concat across the campaign with a
  `timestamp` col). Skips one corrupt zip
  (`2025/20251031/dipdip_line_E_..._fw.zip`). Caches to `ohmpi/cache/`.
- `ohmpi/scripts/test_circuit.py` — validates the ~100 Ω reference resistor
  (`60_61_62_64`) over the whole campaign with the sign-flip half-cycle
  estimator `R = mean(V·pol)/mean(I·pol)`. Daily R holds 99.2/99.8 Ω (fwd/recip)
  all year. `plot_method_compare()` shows off-pulse subtraction is biased per
  half-cycle (+cycle 80 Ω / −cycle 119 Ω) while sign-flip is unbiased (99.3 Ω).
- `ohmpi/scripts/qc_overview.py` — campaign-wide triage from the cheap summary
  table: `quad × time` reciprocal-error heatmaps (one panel per line) and
  per-quad signal-vs-reciprocal scatters, for dipdip and wenner. Replaces
  ~90k per-survey plots with a handful of overview images.
- `ohmpi/scripts/line_e_drilldown.py` — line E investigation: per-electrode
  fault map (recip error + contact resistance), SP(t) cycle-midpoint drift
  diagnostic, SP-slope distribution, raw full waveforms and waveform-over-time.
- `ohmpi/scripts/explore_waveforms.py` — good/bad/reference quad waveform
  comparison for dipdip line A (waveform-over-time, histograms, examples).

### Changed
- `.gitignore` — exclude the two large regenerable OhmPi geometry tables
  (`combinations_with_K.csv` 44 MB, `electrode_combinations.csv` 18 MB).

## 2026-05-23 — 2026-05-26 — presentation prep: tau-by-slope, captured-water budget, PET upgrade, transpiration test, sensor display names

### Added
- `notes/processing_steps.md` — full play-by-play of the pipeline,
  with a top-section convention table mapping raw `SMSnn` IDs to
  the new compact display names (`sw_t_10`, `cn_b_40`, etc.).
- `notes/figures_index.md` — one-paragraph "what/how/why" per
  figure in `plots/`, grouped by pipeline section.
- `notes/presentation_slides.md` — 16-slide Marp deck for the
  presentation: site & hypothesis, coverage caveats (dead rain
  gauge), recession τ slope-paired (3 figures), τ map, Mid/Mound
  overlay, 40 cm amplitudes, tree-transpiration test (PET
  regression), PM-FAO methodology slide, outlook.
- `src/swale/display_names.py` — central `display(sensor_id)` helper
  mapping the raw `SMSnn` IDs to the
  `{sw|cn}_{t|m|b|b1|b2|s}_{10|40}` convention. Raw IDs remain the
  canonical data key; only figure labels change.
- `scripts/07c_recession_tau_by_slope.py` — recession τ
  distributions, slope-paired (Top / Mid / Bottom), common y-axis.
- `scripts/07d_mid_mound_overlay.py` — VWC time series Mound vs
  control Mid, both depths, with long-run means annotated.
- `scripts/07e_event_amplitude_40cm.py` — 40 cm event response
  in three panels: response rate, ΔVWC distribution, count of
  big-amplitude events at two thresholds.
- `scripts/07f_diurnal_dry_season.py` — composite-day diurnal
  cycle of VWC + soil temperature at Mound vs control Mid, both
  depths, two dry-season windows. Uses 24-h centered rolling-mean
  high-pass (not per-calendar-day subtraction, which has a known
  drift-aliasing bug at fast-drying sensors).
- `scripts/07g_pet_dvwc_regression.py` — daily PM-FAO PET vs
  centered first-difference ΔVWC, Mid/Mound + Bottom, both depths,
  with daily and 7-day rolling means. Identifies SMS07 (`sw_b1_40`)
  as the unambiguous transpiration signature (β ≈ −0.6, R² = 0.30).
- `scripts/07h_centered_vs_forward_diff.py` — side-by-side check
  that centered vs forward first difference gives equivalent β.
- `scripts/07i_hourly_pet_regression.py` — hourly PM-FAO PET (FAO
  half-sine disaggregation) vs centered hourly ΔVWC; right column
  is the composite-day stack of hourly ΔVWC, the most diagnostic
  view of the transpiration signature.
- `scripts/07j_captured_water.py` — per-event ΔVWC slope-paired
  with the column-equivalent mm conversion (10 cm sensor →
  0.25 m layer, 40 cm sensor → 0.40 m layer); three panels per
  slope position covering distribution, per-event swale−control
  diff, and cumulative captured-water bar chart.
- `scripts/07k_annualized_water_budget.py` — annualises the
  captured-water totals (94 events / 1.645 yr = 57.1 events/yr)
  to mm/yr/m² and projects to liters at 10/50/200 m² scenarios.
  Writes `plots/07k_annual_water_budget.csv` for re-use.
- `scripts/08b_pet_diurnal_envelope.py` — three-panel PET
  visualisation: full daily record, representative week of
  hourly disaggregation, composite-day envelope.
- `scripts/08c_penman_monteith.py` — full FAO-56 Penman-Monteith
  ETo implementation with reduced-data assumptions (measured T,
  P, ea; assumed u₂ = 2 m/s; Rs estimated from Hargreaves
  Rs formula at K_rs = 0.19 coastal). Outputs `plots/08c_pm_daily.csv`
  and a comparison figure `plots/08c_hs_vs_pm.png`.

### Changed
- **PET default is now Penman-Monteith FAO-56**, not Hargreaves-
  Samani. PM uses our measured air temp, atmospheric pressure,
  and vapour pressure (since 2024-07-23). HS remains as a legacy
  fallback for the early record. Documented in
  `notes/processing_steps.md` §E with full FAO-56 equation
  references (Allen et al. 1998) and the
  measured-vs-assumed inputs table.
- **Sensor labels in figures use the new display names** —
  `sw_t_10`, `cn_b_40`, etc. Updated scripts: `03_spectrogram.py`,
  `04_event_response.py`, `07c–07k` (where applicable),
  `09_sensor_layout.py`, `10_per_location_vwc.py`. Raw `SMSnn`
  remains the data key; only labels change.
- `notes/processing_steps.md` §E rewritten with E1 (HS legacy),
  E2 (PM-FAO default), E3 (hourly disaggregation), plus a full
  references block.

### Findings (informal, from this session)
- **Exponential dominates power-law** for recession-tail fits:
  exp wins 431/470 (92 %) of tails, median R² 0.93 vs 0.79.
- **Slow-drainage signature concentrates at Bottom 1+2.**
  Per-sensor median τ (R² ≥ 0.7, τ ∈ [5, 500] h):
  `sw_b1_40` = 103 h, `sw_b2_40` = 132 h; `cn_b_40` = 54 h.
- **Mid/Mound is wetter at 10 cm but drier at 40 cm than
  control mid.** SMS04 (`sw_m_10`) mean VWC 0.393 vs SMS13
  (`cn_m_10`) 0.363 (+0.030); SMS05 (`sw_m_40`) 0.418 vs
  SMS14 (`cn_m_40`) 0.444 (−0.026).
- **Big-event count (ΔVWC > 0.05) at 40 cm:** control 7 events
  total (3 sensors); swale 17 (5 sensors) → ~2.4× more.
- **Transpiration signature at SMS07** (`sw_b1_40`): PM-FAO
  daily β = −0.51, 7-d β = −0.60, R² = 0.30. Control twin
  SMS16 (`cn_b_40`) sits at β ≈ 0. Robust to the choice of
  PET method (HS gives β = −0.71, R² = 0.30) and finite-
  difference scheme (forward vs centered).
- **Captured-water budget — annualised mm/yr per m² of strip:**
  - Top: control 791, swale 295 → **−496 mm/yr/m²**
  - Mid/Mound: control 340, swale 667 → **+328**
  - Bottom 1: control 567, swale 983 → **+416**
  - Bottom 2: control 567, swale 887 → **+320**
  - Downslope sink (Mound + Bot 1 + Bot 2): **+1 064 mm/yr/m²**
  The swale **redistributes** rather than creates: Top loses
  what the downslope strips gain. Trees at the Mound and Bottom
  benefit from concentrated water at the foot of the slope.
- **Diurnal stacking is dominated by the TEROS-12 T-dielectric
  artifact** at 40 cm (~0.0005 m³/m³ p2p, both treatments).
  Cannot resolve transpiration from sensor noise at this depth
  via diurnal stacking — the PET regression is the right test.

### Known issues
- Hourly regression (07i) currently only covers Bottom 1; should
  be extended to Mid/Mound + Top + Bot 2 to see if any other
  position shows a clean daytime drawdown.
- Slides (`notes/presentation_slides.md`) still reference some
  mixed SMSnn/display-name labels in the prose tables; needs a
  pass.
- PM-FAO PET uses two assumed inputs (wind = 2 m/s; Rs from
  Hargreaves). A cup anemometer + pyranometer would replace
  these with measurements — highest-impact future site upgrade.

## 2026-05-14 — spatial drill-down: sensor layout, DEM, XYZ scans, canonical frame, per-location plots, hillshade

### Added
- `src/swale/sites.py` — `SensorPair` dataclass + `load_sensor_pairs()`
  reading `data/SMS_locations.csv` (3 measurements per pair averaged
  in the source CSV; we use the `_av` columns). Maps each pair to its
  Widmer location (Top slope / Mound / Step / Bottom slope 1+2 for
  the swale; Top / Mid / Bottom slope for the control). Coords are
  returned in the canonical frame (see spatial frame below).
- `src/swale/xyz_streaming.py` — memory-bounded streaming I/O for
  raw `.xyz` point clouds. `summarize_xyz()` (pass 1: extents +
  count) and `histogram2d_xyz()` (pass 2: zsum / count grid).
  Autodetects comma vs whitespace separator; reorders columns
  `(X, V_vert, W_horiz)` → `(X, Y, Z)` for the Y-up raw scan format.
- `src/swale/xyz_align.py` — disk-cached histograms in
  `cache/xyz_histograms/<safe>__NxN.npz` so iterating on rotations
  doesn't restream the 6.6 GB source. `apply_transform()` composes a
  vertical flip with `N × 90°` clockwise rotations (the D4 dihedral
  group), updating both `image` and `extent` consistently.
- **`src/swale/spatial_frame.py`** — single source of truth for
  map-view orientation: **+X = East, +Y = North, +Z = up**. Sign
  multipliers (`raw_x_sign = -1`, `raw_y_sign = -1`) read from
  `config/settings.json:spatial_frame` and applied at load time by
  `load_sensor_pairs`, `load_canonical_dem_mesh`, and the default
  XYZ rotation. With these signs the raw survey frame is rotated
  180° to the canonical one. No `ax.invert_*axis()` calls anywhere
  in the project.
- `src/swale/hillshade.py` — combines the 5 cached dense
  `con_sw_and_for_*` histograms, projects to canonical, crops to the
  DEM mesh bbox, and computes a luminance hillshade via
  `matplotlib.colors.LightSource` (NW illumination, 45° altitude,
  5× vertical exaggeration by default). Reusable as a base layer
  under any plan-view scatter.
- `scripts/09_sensor_layout.py` — plan view of all 8 sensor pairs
  with Widmer location labels, treatment-coloured ring markers,
  Z-as-fill colour, and a 2σ uncertainty ellipse for SMS 10.
- `scripts/10_per_location_vwc.py` — replaces the pooled-by-
  treatment VWC view of `01_data_quality` with a spatially-indexed
  one: one panel per sensor, ordered along the slope (Top → Step →
  Mound → Bottom 1 → Bottom 2 for the swale; Top → Mid → Bottom
  for the control), one figure per depth.
- `scripts/11_per_location_tau.py` — per-sensor median recession τ
  on a plan-view map (one panel per depth). Markers coloured by
  `log10(median τ)`, sized by N good fits; canonical-frame
  hillshade as the base layer; DEM mesh bbox overlaid. Aggregates
  `plots/07_recession_fits.csv` with `R² ≥ 0.7`, `τ ∈ [5, 500] h`,
  `n_good ≥ 3`.
- `scripts/12_dem_views.py` — `Mesh_swale_site.vtk` rendered in 2-D
  (`tripcolor`, no smoothing, 0.10 m contours every line + 0.50 m
  labelled majors) and in 3-D oblique (PyVista, off-screen, 2×
  vertical exaggeration, sensor pairs as coloured spheres).
- `scripts/13_xyz_inventory.py` — per-file streaming summary of all
  raw scans under `data/DEM_xyz/`: point count, extents, mean-Z
  grid per file, combined bounding-box plot, inventory CSV.
  Diagnostic only — stays in the raw scan frame.
- `scripts/14_xyz_aligned.py` — applies the rotation table to bring
  each scan into the canonical frame. Per-file aligned plan view
  PNGs in `plots/14_xyz_aligned/` plus a combined coverage plot.
- `scripts/15_xyz_average_dense.py` — averages the 5 dense
  `con_sw_and_for_*.xyz` scans (28.5 M points each, sub-cm
  registration); reports per-bin std (median 0.1 cm), writes the
  averaged grid, and produces a single-vs-average side-by-side.

### Changed
- `src/swale/config.py` gained `SpatialFrame` and parses the new
  `spatial_frame` section of `settings.json`.
- `scripts/{09,11,12,14,15}` consume canonical-frame data
  directly; no axis-inversion tricks anywhere. The DEM 3-D camera
  position was moved from `(-15, -15, 10)` to `(-25, -25, 10)`
  with a focal point near the canonical sensor cluster so the
  oblique view still looks "from the south-west".
- `config/settings.json` — new `spatial_frame` block:
  ```json
  { "raw_x_sign": -1, "raw_y_sign": -1, "description": "..." }
  ```
- `data/DEM_xyz/` cleanup: kept one representative of the
  redundant dense `con_sw_and_for_*` set + deleted the other 4
  dense duplicates (4 GB) and the sparse `_2_12_44_34.xyz`
  (343 MB). The 5 dense scans share extent to ~sub-cm and per-bin
  Z std of ~1 mm, so averaging buys almost nothing beyond a single
  scan; their cached histograms remain available for hillshade.

### Findings (informal, from this session)
- **Spatial layout matches Widmer Fig. 6 once the frame is set.**
  The swale's "Top slope" is the upstream end of the dug
  construction, not the topographic top of the hillslope — the DEM
  shows the swale sits in the lower terrain, and the control plot
  occupies the higher ground to the east.
- **Z sign anomaly**: 5/8 sensor pairs match local DEM surface
  elevation to within ~5 cm; 3 outliers (SMS 1+2, SMS 3+4+5, SMS
  11+12) sit ~0.33–0.42 m below the DEM surface — close to the 40
  cm install depth, so the surveyor likely recorded the buried-
  sensor elevation rather than the surface marker for those rows.
  Loader returns Z as-is and flags this in its docstring.
- **Per-location recession τ (median across events, R² ≥ 0.7,
  τ ∈ [5, 500] h)**:
  - 10 cm: swale 73–113 h vs control 39–72 h. Slowest at SMS06
    (Bottom slope 1, 113 h) and SMS04 (Mound, 99 h). Swale ~1.5–2×
    slower than control at every location.
  - 40 cm: swale 69–132 h vs control 43–54 h. Slowest at SMS09
    (Bottom slope 2, 132 h) and SMS07 (Bottom slope 1, 103 h).
    SMS05 (Mound) and SMS10 (Step) drain near control rate.
- **The earlier "swale 40 cm τ ≈ 3261 h" headline was a fitting
  artifact**: it came from pooled fits dominated by pathological
  tails where the recession barely fits an exponential. Within
  physically reasonable τ (≤ 500 h), the swale 40 cm runs only
  ~1.5–2× slower than control, with the slow-drainage signature
  concentrating at the **downslope foot** of the swale (Bottom
  slopes 1 + 2) rather than uniformly across the construction.
- **SMS02 (Top slope swale, 40 cm) has only 1 good fit** (τ ≈
  263 h) — the Top slope 40 cm rarely responds enough to fit a
  clean recession. Excluded from the per-location map (n ≥ 3
  threshold) but flagged for follow-up.

### Known issues / open
- The "SMS 6,7 vs SMS 8,9" label/position question in
  `SMS_locations.csv` remains user-owned; user said "I need to
  dig into the data to fix this".
- Hillshade source uses only the 5 dense `con_sw_and_for_*` scans
  (the only multi-scan area). The other 13 raw scans cover
  smaller patches and would each need per-file rotation tuning to
  composite cleanly.

## 2026-05-11 — 2026-05-14 — config, equilibration, CSV check, PET, Widmer mapping, LGAR notes

### Added
- `config/settings.json` — central tunables (equilibration days, data
  paths, treatment colors). 14 d global default for the equilibration
  cutoff with a per-sensor `days_overrides` dict.
- `src/swale/config.py` — `load_settings()`, `apply_equilibration_cutoff`,
  `per_sensor_first_valid`. The equilibration helper drops rows where
  `timestamp < first_valid + days_for(sensor)` for the configured
  variables (`moisture`, `soil_temp`, `bulk_ec`).
- `scripts/check_new_data_dump.py` — unzips `data/All-z6-*.zip` into
  `data/unpacked/<serial>/`, reads via `read_logger_csv`, diffs against
  the cache on (logger, port, variable, timestamp). Writes per-(sensor,
  variable) summary to `plots/check_new_data_dump.csv` and prints
  headline counts + top 20 disagreements. Read-only — does not touch
  the cache.
- `01_data_quality.py: plot_equilibration()` — per-sensor first-N-days
  grid (rows = SMS sensors, cols = moisture/soil_temp/bulk_ec) with the
  cutoff line drawn at `equilibration.days_default`. Output:
  `plots/01_equilibration.png`.
- `scripts/08_pet_hargreaves.py` — daily PET via Hargreaves-Samani
  from the ATMOS-14 air-temp record on logger 19570. Implements
  Widmer §3.4 Eqs. 3–7 with two units corrections (FAO-1998 solar
  constant in MJ/m²/min; Ra converted from MJ/m²/day to mm/day via
  the latent heat of vaporisation). Outputs `plots/08_pet_daily.csv`
  and `plots/08_pet_overview.png` (PET vs daily rainfall).
- `scripts/sensor_mapping_widmer.py` + `plots/sensor_mapping_widmer.csv`
  — cross-check of our SMS01–16 metadata against Widmer (2024) Table 6
  (p. 32) by `(treatment, tag→Widmer-location, depth)`. Two known
  caveats flagged in the script (Widmer's Step 0.1 m sensor 3 has no
  equivalent in our metadata; `down`/`far` → `Bottom slope 1/2` is
  presumed).
- `07_recession_fits.py: plots/07_recession_fits_examples_loglog.png`
  — log-log version of the example tails. Natural view for
  distinguishing exponential from power-law behaviour visually.
- `notes/lgar_design_choices.md` + `config/lgar_setup.json` — working
  reference for reproducing Widmer (2024) with LGAR-Py. Every input
  cited to its thesis section / equation / table.
- `notes/recession_tail_richards.{tex,pdf}` — short derivation of the
  Boussinesq / Richards basis for the exponential vs power-law tail
  fits in `07_recession_fits.py`.

### Changed
- Scripts renumbered to a single linear pipeline (run order = filename
  prefix; outputs share the prefix):
  - `make_plots.py`          → `01_data_quality.py`
  - `spectrum.py`            → `02_spectrum.py`
  - `spectrum_mne.py`        → `02b_spectrum_mne.py`
  - `spectrogram.py`         → `03_spectrogram.py`
  - `event_response.py`      → `04_event_response.py`
  - `01_rising_limb_metrics` → `05_rising_limb_metrics`
  - `03_wetting_front_lag`   → `06_wetting_front_lag`
  - `04_recession_fits`      → `07_recession_fits`
  Plot outputs renamed accordingly (`weather.png` → `01_weather.png`,
  `spectrogram_10cm_mexh.png` → `03_spectrogram_10cm_mexh.png`, etc.).
- All analysis scripts now read `DATA_ROOT` and `METADATA` from
  `config/settings.json` via `load_settings()` instead of hardcoded
  paths. The metadata location moved from `/home/alexis/DATA/swale/
  Metadata.xlsx` to `data/Metadata.xlsx` (the user's latest copy).
- `.gitignore`: added `data/` (raw zip dumps and unpacked CSVs), the
  LibreOffice `.~lock.*#` pattern, `external/` (vendored LGAR-Py
  reference checkout), the Widmer thesis PDF, and the LaTeX build
  artifacts under `notes/`.

### Findings (informal, from this session)
- Mean Hargreaves-Samani PET ≈ 4–5 mm/day (≈ 1500–1800 mm/yr) over
  the observed record — higher than Widmer's cited Thornthwaite
  estimate of ~2.3 mm/day (855 mm/yr; 63 % of rainfall). Likely
  because Hargreaves-Samani over-predicts in humid/tropical climates
  unless calibrated; worth flagging before any model forcing.
- New CSV portal dump extends coverage from 2026-02-04 → 2026-05-11
  (~3 months past the existing cache).
- Moisture agrees with the cache within 3-decimal CSV display rounding
  (median disagreement ~0.001 m³/m³; effectively zero divergences past
  tolerance). The hybrid XLSX-preferred loader is the right call —
  switching to CSV-only would only save the bulk_ec aliasing artifact.
- bulk_ec disagreements (~56k per sensor on 05511) are the known
  XLSX "Bulk EC" vs CSV "Saturation Extract EC" semantic mismatch.
  No change of that picture from the new dump.
- SMS10 decision: keep as the 5th swale-40 cm sensor. The `Step??`
  location and `tag = step` are noted but the explicit `treatment =
  swale` and `depth = 40` are honored as authoritative.
- SMS17–22 don't exist in the metadata; SMS23/24 already excluded
  via null treatment. Nothing to change for "drop SMS17–24".

### Known issues (new this session)
- Logger 19574, port 3+ (SMS06 + SMS08): the XLSX side of the cache
  reports systematically wrong `soil_temp` from 2024-11-29 to
  2025-05-02 (median diff 1.7–3 °C, max 9 °C; v_cache appears stuck
  at 25.5 °C). Likely one bad XLSX snapshot winning dedup. Tracked
  but not fixed this session.
- The cache has a tagging anomaly on `ATMOS14_19570`: a subset of
  rows are stored with `sensor_type = 'TEROS12'` for
  moisture/soil_temp/bulk_ec — almost certainly a port-5 collision
  between an early CSV (TEROS12) and the current XLSX (ATMOS14).
  `01_data_quality.plot_equilibration` filters to `SMS*` IDs as a
  defensive workaround; the underlying typing is still wrong.

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
