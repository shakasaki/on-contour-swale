# Changelog

All notable changes to the swale project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
