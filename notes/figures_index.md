# Figures index

One-paragraph "what / how / why" per figure in `plots/`. Grouped by
pipeline section. Filenames are the source of truth; if a figure isn't
listed here it's a diagnostic, not a presentation figure.

---

## A. Data quality

**`01_weather.png`** — Weather panel for logger 19570: air temperature,
atmospheric pressure, vapor pressure, VPD, rain. *How:* one row per
variable from the ATMOS-14 + ECRN-100 long-form cache. *Why:* establishes
the climate-forcing record and visually confirms the rain-gauge stall
(continuous zero from 2025-06-22 onwards).

**`01_soil.png`** — Soil moisture / temperature / EC for every SMS sensor,
split by depth × treatment grid. *How:* full record after the
14-day equilibration cutoff. *Why:* the bird's-eye view of every sensor's
behaviour over time.

**`01_equilibration.png`** — Per-sensor first-21-days panel grid (rows
= SMS sensors, cols = moisture/soil_temp/bulk_ec) with the cutoff
line drawn at 14 d. *Why:* justifies the equilibration trim — sensors
settle in 1–4 d but a few drift for >1 week.

## B. Rain events

**`00_events_from_soil_validation.png`** — Rain trace + 10 cm VWC for
all responding sensors + onset rug for detected events, restricted
to the gauge-valid window. *How:* output of the soil-moisture event
detector validated against the rain-gauge record (precision/recall
sweep over the 94 events). *Why:* visual proof that VWC-based event
detection is reliable enough to substitute for the dead rain gauge
after 2025-06-22.

## C. Time-frequency (exploratory)

**`02_spectrum.png` / `02_spectrum_long.png` / `02b_spectrum_mne.png`** —
Welch PSD per sensor / depth / treatment (7-day and full-record
windows, scipy + MNE backends). *Why:* attempt to detect treatment
differences in frequency space. *Result:* the diurnal band is clear
but treatment differences are not visually obvious. Kept as appendix.

**`03_spectrogram_{10,40}cm{,_morlet,_mexh}.png` + `03_spectrogram_overview.png`** —
Wavelet TFR per sensor (Morlet / Mexican-hat / cmor). *Why:* time-
resolved frequency content around rain events. *Result:* diurnal
modulation and event cones visible, but time-domain recessions
(§D) are more discriminating. Appendix material.

## D. Per-event metrics — central analysis

**`04_event_20250611.png`** — Time-domain response of every sensor
around the 2025-06-11 rain event. *Why:* concrete illustration of
how swale vs control 40 cm differ on a single large event.

**`05_rising_limb_metrics.png`** — Boxplot grid of ΔVWC, time-to-peak,
mean dVWC/dt per event × sensor. *Why:* quantifies how much each
sensor wets per event and how fast — the input to D2 in the
processing-steps doc.

**`06_wetting_front_lag.png`** — 10 cm → 40 cm onset and peak lag for
the 7 paired locations. *Why:* tests whether the swale slows down
the vertical wetting front compared to the control.

**`07_recession_fits_examples.png`** — Best-R² recession tail per
depth × treatment, linear scale, with both exponential and power-law
fits overlaid. *Why:* visual proof of "good fits" — the exemplar
illustrating the model that wins.

**`07_recession_fits_examples_loglog.png`** — Same tails on log-log
axes. *Why:* exponential straightens on `log(VWC − C)` vs `t`,
power-law straightens on `log` vs `log(t − t_peak)`. Direct visual
diagnosis of which functional form fits.

**`07_recession_fits_distributions.png`** — Boxplot of τ, α, exp-R²,
pow-R² across all fits, split by depth × treatment. *Why:* original
"pooled" view comparing the two functional forms. Quantifies the
exp-wins result (median R² 0.93 vs 0.79; exp better in 431/470
fits). **Superseded for the swale-vs-control story by the
slope-paired figures below — keep this one only for the model
comparison.**

**`07_recession_representative_events.png`** — Full event windows
(event_start → next_event_start) for the 3 largest clean events,
showing the time-domain swale-vs-control contrast at 10 cm and 40 cm.
*Why:* "feel" the recession contrast on real events instead of
through summary statistics.

**`07c_tau_by_slope_{top,mid,bottom}.png`** — Box+strip of recession τ
for swale and control sensors at the same slope position. Three
figures, common y-axis. *How:* reads `plots/07_recession_fits.csv`,
filters R² ≥ 0.7 and τ ∈ [5, 500] h, groups by slope position
(Top = SMS11/12 vs SMS01/02; Mid/Mound = SMS13/14 vs SMS04/05;
Bottom = SMS15/16 vs SMS06–09). *Why:* pooling all swale vs all
control hides the spatial gradient — the Mound, Step, and Bottom-
slope sensors do not drain on the same timescale. These figures
keep each comparison spatially fair.

**`07d_mid_mound_overlay.png`** — VWC time series at SMS04+SMS13
(10 cm) and SMS05+SMS14 (40 cm), with long-run means as dashed
lines. *How:* full post-equilibration record, zero-dropouts removed.
*Why:* directly tests the "Mound retains more water" intuition.
Result: holds at 10 cm (Mound +0.030 m³/m³ on the mean vs control
Mid), *flips* at 40 cm (Mound −0.026, and a much wider dry-season
swing). Sets up the tree-transpiration hypothesis.

**`07e_event_amplitude_40cm.png`** — 40 cm event-response quantification
in 3 panels: (a) response rate per sensor, (b) per-event ΔVWC
distribution (box+strip), (c) count of events above ΔVWC = 0.02 and
0.05 thresholds. *Why:* tests the visual observation that "swale 40 cm
spikes higher and has more big events than control". Result: response
*count* is similar between treatments, but **amplitudes are ~2× bigger
at the swale Mound (SMS05) and Bottom 1 (SMS07), and big-event count
(ΔVWC > 0.05) is 2.4× higher overall in the swale**.

**`07g_pet_vs_dvwc_{mid_mound,bottom}.png`** — Daily dry-season ΔVWC
regressed against **Penman-Monteith FAO-56** PET, two slope
positions, both depths, both treatments. *How:* daily mean VWC,
**centered** first difference (2nd-order accurate), joined on date
with PM-FAO PET (`08c_pm_daily.csv`; falls back to HS pre-2024-07-23
when ATMOS-14 vapour pressure wasn't yet logging), filtered to
2024-12-01 → 2025-04-30 with rain < 1 mm; OLS slope β and R² for
both raw daily and 7-day centered rolling-mean series. *Why:* clean
physical test of the tree-transpiration hypothesis — more negative
β means more PET-driven water loss = more transpiration. *Result:*
**SMS07 (Bottom 1 swale, 40 cm) is the unambiguous transpiration
signature** — β ≈ −0.6 with PM (≈ −0.7 with HS), consistent across
daily and 7-d scales, R² rises to 0.30 with smoothing. Control twin
SMS16 sits at β ≈ 0 either way. Conclusion is invariant to PET
model and differencing scheme.

**`07h_centered_vs_forward.png`** — Forward vs centered first
difference for ΔVWC at the four Bottom-slope 1 sensors. *How:*
overlay raw scatter of both schemes with their OLS fits and β / R².
*Why:* methodological check — the two schemes give effectively
identical β where the signal exists. Centered is the default
going forward (small noise win, 2nd-order accuracy).

**`07i_hourly_pet_regression.png`** — Hourly PM-FAO PET (FAO §3.5
half-sine disaggregation) vs centered hourly ΔVWC at SMS06/07
(swale Bot 1) and SMS15/16 (control), both depths. *How:* 5-min
VWC resampled to hourly mean (≥ 9 of 12 samples per hour required);
centered hourly first difference; hourly PET disaggregated from
daily PM-FAO totals; joined on (date, hour); regression with daytime
∪ nighttime hours. *Right column:* composite-day stack of hourly
ΔVWC by hour-of-day (median + IQR) — visualises the daytime
drawdown / nighttime flat signature that transpiration should
produce. *Why:* eliminates the vertical-line artifact of the daily
regression and provides a much higher-resolution view of the
PET ↔ VWC coupling.

**`07f_diurnal_dry_season.png`** — Dry-season diurnal cycle of VWC
and soil-temperature at Mound (SMS04/SMS05) vs control Mid
(SMS13/SMS14), both 10 cm and 40 cm, early vs late dry windows.
*How:* **high-pass at 24 h via a centered 288-sample (5-min × 24 h)
rolling-mean subtraction**, then composite-stack the residuals by
hour-of-day with median + IQR. *Crucially not* the naive
per-calendar-day mean subtraction — that aliased the within-day
secular drying onto the diurnal axis and produced spurious
phase-flipped cycles. *Why:* test for tree-transpiration signature
on the Mound (daytime drawdown / overnight recovery). *Result:* at
40 cm the diurnal signal sits at the TEROS-12 dielectric T-
dependence floor (~0.0003 m³/m³ per °C × ~1 °C swing); both sensors
look similar; can't resolve transpiration. At 10 cm the cycles are
larger but **SMS13 (control) shows an inverted, large-amplitude
cycle** likely due to the sign-of-T-dependence flipping with soil
texture / moisture range; SMS04 (Mound) shows a smaller cycle with
the expected morning-peak / afternoon-trough phase. The diurnal
test alone is therefore inconclusive — next step is regressing
daily dry-season `dVWC/dt` against Hargreaves-Samani PET.

## E. Climate forcing

**`08_pet_overview.png`** — Daily Hargreaves-Samani PET (mm/day)
vs daily rainfall over the observed record. *How:* PET computed from
ATMOS-14 air-temp only; `Ra` modelled from Julian day + latitude
(no measured solar radiation on-site). *Why:* legacy figure used to
visualise the temperature-only HS form. **Superseded by 08c for the
default PET — kept for backward compatibility with Widmer (2024).**

**`08b_pet_diurnal_envelope.png`** — Three panels: (a) full daily HS
PET time series with dry-season window shaded; (b) representative
week (2025-02-10 → 17) disaggregated to hourly via FAO-56 §3.5
half-sinusoid; (c) composite-day envelope (median + IQR + min/max)
across the dry-season record. *Why:* sanity-check that the PET
shape follows the sun cycle (it does — clean half-sine peaking at
~0.7 mm/h at solar noon) and shows how we project daily totals to
hourly for the high-resolution regression in §G2.

**`08c_hs_vs_pm.png`** — Penman-Monteith FAO-56 vs Hargreaves-Samani
PET — time series, scatter, daily ratio, stats. *How:* PM
implementation in `scripts/08c_penman_monteith.py` with
"reduced-data" assumptions (assumed `u₂ = 2 m/s`, estimated `Rs`
from Hargreaves' temperature formula). *Why:* establishes PM-FAO
(the international standard) as the default PET; HS over-predicts
by the expected ~10–30 % in this humid-tropical climate. The
SMS07 transpiration result is robust to the choice of method.

## F. Topography

**`12_dem_xy.png`** — `Mesh_swale_site.vtk` rendered top-down with
0.10 m contours every line + 0.50 m labelled majors. *Why:* the
top-down topographic map of the site, in the canonical (+X = East,
+Y = North) frame.

**`12_dem_3d.png`** — PyVista oblique view of the same DEM, 2×
vertical exaggeration, sensor pairs as coloured spheres. *Why:*
3-D visualisation to convey the swale's geometry on the slope.

**`15_xyz_averaged.png` + `15_xyz_average_vs_single.png` + `15_xyz_stddev_per_bin.png`** —
Averaged surface from the 5 dense `con_sw_and_for_*.xyz` scans
(28.5 M points each). *How:* memory-bounded streaming, common bin
grid, mean + std per bin. *Why:* justifies treating the 5 scans as
independent measurements of the same surface (median per-bin Z std
≈ 1 mm). Feeds the hillshade in §H.

**`13_xyz_coverage.png` + `14_xyz_aligned_coverage.png`** — Per-scan
plan-view coverage (raw frame, and after the rotation table is
applied). *Why:* sanity check that the rotation table lines up all
17 scans into the canonical frame.

## H. Spatial drill-down

**`09_sensor_layout.png`** — Plan-view map of all 8 sensor pairs with
Widmer-thesis location labels, treatment-coloured ring markers,
Z-as-fill colour, and a 2σ uncertainty ellipse for SMS 10. *Why:*
"where is everything on the slope" — the spatial anchor for every
other map figure.

**`10_per_location_vwc_{10,40}cm.png`** — One panel per sensor, VWC
time series, ordered along the slope (Top → Step → Mound → Bottom
1 → Bottom 2 for the swale; Top → Mid → Bottom for the control).
*Why:* spatially indexed companion to `01_soil.png` — replaces the
pooled-by-treatment view with one that shows the slope gradient
directly. The 40 cm version is what prompted the "swale has more
big events than control" observation that 07e quantified.

**`11_per_location_tau_map.png`** — Median exponential recession τ
on a hillshaded plan view (one panel per depth). *How:* aggregates
`07_recession_fits.csv` with R² ≥ 0.7, τ ∈ [5, 500] h, n_good ≥ 3;
markers coloured by `log10(median τ)`, sized by N good fits;
canonical-frame hillshade as the base layer; DEM mesh bbox overlaid.
*Why:* **the hero figure** — reveals that the slow-drainage
signature at swale 40 cm concentrates at Bottom slope 1+2
(SMS07 τ=103 h, SMS09 τ=132 h), not uniformly across the swale.
Refines the earlier "swale 40 cm τ ≈ 3261 h" pooled headline.

---

## Diagnostic / not for presentation

`diag_bulk_ec.png`, `diag_moisture.png`, `diag_soil_temp.png` —
per-sensor source-coloured overlays for cross-source diff checking
(loader internals). `first_two_weeks.png` — early equilibration
exploration; superseded by `01_equilibration.png`.

**`allrange_{soil,weather,housekeeping}_NN_YYYYMM-YYYYMM.png`** — full-record
walk-through: every variable in consecutive 6-month windows from the first
reading (2024-05), one figure per data-type group per window. *How:*
`scripts/14_all_data_by_6mo.py`; hourly-mean line + hourly min–max shaded
band, flagged readings (`error_code != 0`) nulled first; soil coloured by
treatment and dashed by depth, housekeeping coloured by logger. *Why:* a
no-cutoff eyeball pass over the whole raw record to spot gaps, steps, sensor
deaths and seasonal structure before any analysis.
