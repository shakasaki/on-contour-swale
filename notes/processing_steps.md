# Processing & analysis steps

How we got from raw METER ZL6 exports + LiDAR scans to the present
results. Run order = filename prefix in `scripts/`.

## Sensor display-name convention

Figure labels use a compact convention rather than the raw `SMSnn`
IDs from the METER metadata. Pattern: `{treatment}_{position}_{depth_cm}`.

| Raw ID | Display | Treatment / position / depth |
|---|---|---|
| SMS01 | `sw_t_10` | swale, Top slope (SwB), 10 cm |
| SMS02 | `sw_t_40` | swale, Top slope (SwB), 40 cm |
| SMS04 | `sw_m_10` | swale, Mound (SwD), 10 cm |
| SMS05 | `sw_m_40` | swale, Mound (SwD), 40 cm |
| SMS06 | `sw_b1_10` | swale, Bottom slope 1 (SwE), 10 cm |
| SMS07 | `sw_b1_40` | swale, Bottom slope 1 (SwE), 40 cm |
| SMS08 | `sw_b2_10` | swale, Bottom slope 2 (SwF), 10 cm |
| SMS09 | `sw_b2_40` | swale, Bottom slope 2 (SwF), 40 cm |
| SMS10 | `sw_s_40` | swale, Step, 40 cm (10 cm pair never installed) |
| SMS11 | `cn_t_10` | control, Top, 10 cm |
| SMS12 | `cn_t_40` | control, Top, 40 cm |
| SMS13 | `cn_m_10` | control, Mid, 10 cm |
| SMS14 | `cn_m_40` | control, Mid, 40 cm |
| SMS15 | `cn_b_10` | control, Bottom, 10 cm |
| SMS16 | `cn_b_40` | control, Bottom, 40 cm |

`SMS03` is intentionally omitted — its metadata depth is recorded as
`-10 cm` (likely a data-entry error in the source XLSX) and it has
no place in any slope-paired analysis.

Mapping + lookup helpers live in
[`src/swale/display_names.py`](../src/swale/display_names.py). The
raw `SMSnn` IDs remain the canonical key for the parquet cache,
metadata, and slope-grouping configs in the scripts; only the
display layer changes.


---

## A. Ingestion & data quality

### Pipeline

1. **Parse `Metadata.xlsx`** (`src/swale/metadata.py`).
   Builds the (logger, port) → sensor map. Handles the stacked
   `Serials` layout, drops Forest sensors + logger 05533, normalises
   IDs (`SMS 16` → `SMS16`), reads `tag` / `treatment`, and synthesises
   rows for logger-internal channels + ATMOS-14 / ECRN-100 on logger
   19570.

2. **Read per-logger CSVs and XLSX snapshots** (`src/swale/readers.py`).
   Both produce the same long schema. Handles the 3-row header, the
   multiple `Processed Data Config N` Excel sheets, ASCII/Unicode
   units, and unsorted rows.

3. **Build the unified long dataset** (`src/swale/loader.py`).
   Joins metadata; deduplicates with **XLSX preferred over CSV** (CSV
   is 3-decimal display-rounded; XLSX carries full precision); drops
   implausible-year timestamps; warns on cross-source disagreement
   with combined abs+rel tolerance; reindexes to a 5-min grid; caches
   as Parquet partitioned by logger.

4. **Equilibration cutoff** (`src/swale/config.py`).
   Drops the first 14 days after each sensor's first valid reading
   (per-sensor overrides in `config/settings.json`).

### Coverage & missing data

All TEROS-12 soil sensors run from **April–May 2024 to 2026-02-03**
(last cache refresh). Cadence is 5 min, regular for every sensor on
loggers 19574 and the control side of 19570 (gaps ≪ 1 %).

| Sensor pair | Logger | Start | Missing |
|---|---|---|---|
| SMS01 / SMS02 (SwB) | 19570 | 2024-04-23 | 5.0 % |
| SMS03 / SMS10 (SwD top + Step) | 19570 | 2024-04-24 | 5.2 % |
| SMS04–SMS09 (swale rest) | 19574 | 2024-05-23 | 0.1 % |
| SMS11–SMS16 (control) | 19570 | 2024-05-25 | 0.4 % |

The "5 %" on SMS01–03 + SMS10 is **one 31–33 day outage in late
April/early May 2024** at the start of the record, plus a handful of
5–10 h gaps clustered around 2025-02-12 to 2025-02-16. Everything
outside those windows is on the regular grid.

### Dead / partial sensors

- **Rain gauge (ECRN-100 on logger 19570) is dead from 2025-06-22
  22:15 onward.** Last non-zero tip is at that timestamp. The logger
  keeps emitting 0.0 mm at 5-min cadence (no nulls), so the data flow
  is healthy — but mechanically the gauge is silent (jam or detached
  lead). **Any rain-forced analysis is bounded above by 2025-06-22.**
  After that date we rely on the VWC-based event detector (§B).
  Monthly totals confirm the diagnosis:

  ```
  2024-08  323 mm   2025-05    61 mm   2025-08–2026-02   0 mm
  2024-10  217 mm   2025-06    58 mm   (continuous zeros)
  ```

- **ATMOS-14 humidity channel drops out 2025-02-04.** `air_temp`,
  `atm_pressure`, `vapor_pressure`, and `vpd` keep running through
  2026-02-03. PET only needs `air_temp`, so this doesn't constrain
  the climate-forcing step.

- **`vapor_pressure` / `vpd` start late** (2024-07-23 vs the rest of
  the ATMOS-14 at 2024-05-26). Not used in the current analysis.

- **SMS02 (Top slope swale, 40 cm) has only 1 good recession fit**
  in the cleaned set — the Top slope 40 cm rarely responds enough
  to fit a clean tail. Flagged but kept in the time series.

- **SMS 6,7 vs SMS 8,9 label/position in `SMS_locations.csv`** is
  still open (user-owned).

---

## B. Rain events from VWC

5. **Detect rain events from soil moisture** (`00_detect_events_from_soil.py`,
   `src/swale/events.py`). Necessary because the rain gauge is dead
   for the second half of the record. Smoothed centered-difference
   `dVWC/dt` per 10 cm sensor, K-of-N consensus across sensors, gap
   coalescence. **94 events** detected over the full record.
   Validated against the rain-gauge record over the gauge-valid window
   (start → 2025-06-22): **76 % precision, 86 % recall** on gauge
   events ≥ 10 mm. Misses are dominated by sub-2 mm tips that don't
   move the VWC signal.

---

## C. Time-frequency (exploratory, not central)

Attempted as a way to detect events or treatment differences not
visible in the time domain.

- Welch PSD per sensor / depth / treatment (`02_spectrum.py`,
  `02b_spectrum_mne.py`).
- Wavelet TFR per sensor (`03_spectrogram.py`): Morlet + Mexican-hat
  + cmor.

**Outcome:** the diurnal band and event cones are visible, but the
treatment difference is not visually obvious in the TFR. Everything
discriminative shows up more clearly in the **time-domain recession
curves (§D)**. The frequency-domain step is reported as a methodology
note; figures stay in the appendix.

---

## D. Per-event metrics — the central analysis

For every detected event we extract a per-sensor time-domain
fingerprint. Three pieces.

### D1. Detection threshold & peak finding

For each event window:
- **Event onset** comes from the soil-moisture detector (§B): a
  smoothed `dVWC/dt` rising above a per-sensor threshold, confirmed
  by K-of-N consensus across the 10 cm sensors.
- **Peak** is the local maximum within a fixed search window after
  onset (per sensor, per depth).
- The window from event start to the peak defines the **rising
  limb**; from the peak to (next event start − 2 h), capped at 7 d,
  defines the **recession tail**.

### D2. Rising-limb metrics (`05_rising_limb_metrics.py`)

Per (event × sensor): baseline VWC, peak VWC, **ΔVWC**, **time-to-peak**,
**mean `dVWC/dt`** during the rise. Output:
`plots/05_rising_limb_metrics.{csv,png}`.

Headline numbers at **10 cm**:
- Swale ΔVWC median **0.029** vs control **0.019** — the swale wets
  more per event.
- Time-to-peak and rise rate are similar order of magnitude across
  treatments at 10 cm.

### D3. Recession-tail fits (`07_recession_fits.py`)

Fitted on each tail with `scipy.curve_fit`:
- **Exponential**: `A · exp(-t/τ) + C`
- **Power-law**:   `A · (t − t_peak)^(-α) + C`

Across the **470 fitted tails**:

| Model | Median R² | Wins on |
|---|---|---|
| Exponential | **0.93** | **431 / 470** tails (92 %) |
| Power-law | 0.79 | 39 / 470 |

**The exponential wins clearly.** Power-law tails do appear, but
they're a minority and concentrate on already-poor fits. We report τ
from the exponential model.

Figures to show:
- `plots/07_recession_fits_examples.png` — **good fits** (best-R²
  per depth × treatment) in linear scale.
- `plots/07_recession_fits_examples_loglog.png` — same on log-log;
  exponential is straight on a `log(VWC − C)` y-axis, power-law on
  log-log.
- `plots/07_recession_fits_distributions.png` — distribution of τ
  and α across all fits, by depth × treatment. Good place to point
  out the long-tailed τ histogram.
- `plots/07_recession_representative_events.png` — full event windows
  for the 3 largest clean events, showing the swale-vs-control
  recession contrast at 40 cm.

**Per-sensor table (R² ≥ 0.7, τ ∈ [5, 500] h, 302 / 470 fits):**

| Depth | Treatment | Sensor (location) | n | median τ [h] | IQR [h] |
|---|---|---|---|---|---|
| 10 cm | control | SMS11 (Top) | 46 | 54 | 26 – 97 |
| 10 cm | control | SMS13 (Mid) | 22 | 39 | 20 – 88 |
| 10 cm | control | SMS15 (Bottom) | 32 | 72 | 26 – 112 |
| 10 cm | swale | SMS01 (Top) | 18 | 73 | 21 – 119 |
| 10 cm | swale | SMS04 (Mound) | 17 | 99 | 59 – 182 |
| 10 cm | swale | SMS06 (Bottom 1) | 49 | 113 | 31 – 201 |
| 10 cm | swale | SMS08 (Bottom 2) | 42 | 76 | 25 – 110 |
| 40 cm | control | SMS12 (Top) | 22 | 50 | 35 – 96 |
| 40 cm | control | SMS14 (Mid) | 8 | 43 | 24 – 82 |
| 40 cm | control | SMS16 (Bottom) | 13 | 54 | 27 – 74 |
| 40 cm | swale | SMS02 (Top) | 1 | 263 | — *(n=1, exclude)* |
| 40 cm | swale | SMS05 (Mound) | 9 | 68 | 61 – 179 |
| 40 cm | swale | SMS07 (Bottom 1) | 10 | **103** | 69 – 167 |
| 40 cm | swale | SMS09 (Bottom 2) | 6 | **132** | 11 – 252 |
| 40 cm | swale | SMS10 (Step) | 7 | 69 | 62 – 95 |

**Reading the table:**
- At 10 cm, the swale drains ~1.5–2× slower than the control at
  **every** location.
- At 40 cm, the slow drainage **concentrates at the downslope foot
  of the swale** (SMS07 + SMS09, Bottom slope 1 + 2). The Mound
  (SMS05) and Step (SMS10) drain at near-control rates.
- The earlier headline "swale 40 cm τ ≈ 3261 h" was a pooled-fit
  artifact dominated by pathological tails where the recession barely
  fits an exponential at all. With R² ≥ 0.7 and τ ≤ 500 h the
  signature is **spatial, not uniform**.

---

## E. Climate forcing — potential evapotranspiration

We compute **two** daily-PET series and keep both for traceability,
but the **Penman-Monteith FAO-56** form is the default reference for
all downstream analyses (LGAR forcing, the PET ↔ ΔVWC regression
in §G2).

| Method | Script | Output | Role |
|---|---|---|---|
| Hargreaves-Samani (HS) | `scripts/08_pet_hargreaves.py` | `plots/08_pet_daily.csv` | fallback, comparable to Widmer (2024) |
| Penman-Monteith FAO-56 | `scripts/08c_penman_monteith.py` | `plots/08c_pm_daily.csv` | **default** |

### E1. Hargreaves-Samani (kept for legacy + early-record coverage)

Implements the temperature-only form (Hargreaves & Samani 1985,
formalised in FAO-56 §5; Allen et al. 1998, Eq. 52):

> `ETo = 0.0023 · √(T_max − T_min) · (T_mean + 17.8) · Ra_mm`

with extraterrestrial radiation `Ra(J, φ)` from solar geometry
(FAO-56 Eqs. 21–25) and `Ra_mm = Ra_MJ / λ` where `λ = 2.45 MJ/kg`
(latent heat of vaporisation; Allen et al. 1998 Eq. 20).

**Why we kept this.** It's exactly what Widmer (2024) §3.4 used,
which makes our results comparable to her thesis. It's also the
only PET we can compute before 2024-07-23 (when the ATMOS-14
vapour-pressure channel started logging) — so it's the fallback for
the early record.

**Two unit corrections** to Widmer's printed equations:

1. **Solar constant in MJ/m²/min, not MJ/m²/day.** Widmer's text
   gives `G_sc = 0.82 MJ/m²/day`, but the `(24·60/π)` prefactor in
   her Eq. 4 expects MJ/m²/min. With 0.82 the resulting `Ra` is a
   factor 1440 too small. We use the FAO-1998 value
   `G_sc = 0.0820 MJ/m²/min` (FAO-56 §3.5).
2. **`Ra` converted to mm/day in the HS formula.** Widmer's Eq. 3
   has `Ra` in MJ/m²/day; the dimensionally consistent form uses
   `Ra_mm = Ra_MJ / 2.45` (Allen et al. 1998 Eq. 20). With this
   conversion ETo comes out in mm/day.

Mean HS PET ≈ **4–5 mm/day** (≈ 1500–1800 mm/yr).

### E2. Penman-Monteith FAO-56 — the reference method

The international standard for reference evapotranspiration since
1998 (Allen et al. 1998 FAO Irrigation & Drainage Paper 56, Eq. 6):

```
        0.408 · Δ · (Rn − G) + γ · (900 / (T + 273)) · u₂ · (es − ea)
ETo  =  ────────────────────────────────────────────────────────────
                       Δ + γ · (1 + 0.34 · u₂)
```

where Δ is the slope of the saturation vapour-pressure curve
(kPa/°C; FAO-56 Eq. 13), γ is the psychrometric constant (kPa/°C;
FAO-56 Eq. 8), Rn is daily net radiation (MJ/m²/day; FAO-56 §3.6),
G is the soil heat flux (≈ 0 for daily; FAO-56 §3.7), u₂ is wind
speed at 2 m, `es` and `ea` are saturation and actual vapour
pressure (FAO-56 Eqs. 11–12 and §3.4 respectively).

#### Measured vs assumed inputs

| Quantity | Source | Status |
|---|---|---|
| `T_max`, `T_min`, `T_mean` (daily) | ATMOS-14 air-temp on logger 19570 | **measured** (5-min, aggregated daily) |
| Atmospheric pressure `P` (kPa) | ATMOS-14 atm_pressure | **measured** |
| Actual vapour pressure `ea` (kPa) | ATMOS-14 vapor_pressure | **measured** (since 2024-07-23) |
| Wind speed `u₂` (m/s) | — no anemometer on-site | **assumed 2 m/s** (FAO-56 §3.3 default) |
| Solar radiation `Rs` (MJ/m²/day) | — no pyranometer on-site | **estimated** from `T_max − T_min` (FAO-56 Eq. 50): `Rs = K_rs · √(T_max − T_min) · Ra`, with `K_rs = 0.19` (coastal value per FAO-56 §3.5.4 — Auroville is ~10 km from the Bay of Bengal) |
| Net radiation `Rn` (MJ/m²/day) | derived | from `Rs` via FAO-56 Eqs. 37–40 (albedo α = 0.23 for reference grass, clear-sky `Rso = (0.75 + 2·10⁻⁵·z) · Ra`, elevation z ≈ 30 m) |
| Extraterrestrial radiation `Ra` (MJ/m²/day) | computed | latitude + Julian day (FAO-56 Eqs. 21–25, same as HS) |
| Soil heat flux `G` | — | ≈ 0 for daily timesteps (FAO-56 §3.7) |

#### Why this is the right upgrade for us

- **Uses all our atmospheric measurements** (pressure + vapour
  pressure) rather than discarding them.
- **Energy-balance-grounded.** HS is empirical-temperature only and
  is known to over-predict in humid tropics by 30–50 %
  (Tabari 2010; Sentelhas et al. 2010); PM-FAO is the reference
  against which other methods are validated.
- **Comparable to other studies.** PM-FAO is the FAO and WMO
  reference for "reference ETo" used in hydrologic modelling
  (LGAR-Py expects ETo of this form).
- **Robust to PET-model choice in our key result.** Re-running the
  SMS07 transpiration regression with PM in place of HS gives the
  same physical conclusion: 7-d β = −0.60 with PM vs −0.71 with HS,
  R² = 0.30 either way (see §G2). The β is slightly less steep
  because PM's range is wider (1.6–7.3 vs 1.6–6.6 mm/day) but the
  control still sits at β ≈ 0 either way.

#### Result

Mean PM-FAO PET, and direct comparison with HS, are summarised in
`plots/08c_hs_vs_pm.png`. The median PM/HS ratio is < 1 (HS over-
predicts by the expected ~10–30 %), and PM has a wider day-to-day
dynamic range because it tracks the VPD term separately from the
radiation term.

#### What it would take to do better

A **cup anemometer** is the single highest-impact upgrade — it
would replace the `u₂ = 2 m/s` assumption with a measurement.
After that, a **pyranometer** would replace the Hargreaves Rs
estimate with measured Rs. These are both modest sensors (~$100
each) that would dramatically tighten the PET estimate.

### E3. Hourly disaggregation

For the hourly transpiration test in §G2 we disaggregate daily PET
to hourly via the FAO-56 §3.5 / Eq. 53 half-sinusoid:

```
PET_hour(t) = (π · PET_daily / (2 · N)) · sin(π · (t − t_rise) / N)
              for t in [t_rise, t_sunset]; 0 otherwise
```

where daylength `N` and sunrise/sunset are computed from solar
geometry (`ω_s = arccos(−tan φ · tan δ)`; FAO-56 Eqs. 25–26).
Integral across daylight equals PET_daily exactly, so no energy is
added or removed in the disaggregation.

### References

- **Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998).**
  *Crop evapotranspiration — Guidelines for computing crop water
  requirements.* FAO Irrigation and Drainage Paper 56, Rome.
  (Cited throughout; the canonical reference for PM-FAO and the
  Hargreaves Rs estimate.)
- **Hargreaves, G.H. & Samani, Z.A. (1985).** *Reference crop
  evapotranspiration from temperature.* Applied Engineering in
  Agriculture 1: 96–99.
- **Tabari, H. (2010).** *Evaluation of reference crop
  evapotranspiration equations in various climates.* Water
  Resources Management 24: 2311–2337. (Compares HS, PM, Turc,
  Priestley-Taylor across climates — confirms HS over-predicts in
  humid environments.)
- **Sentelhas, P.C., Gillespie, T.J., Santos, E.A. (2010).**
  *Evaluation of FAO Penman-Monteith and alternative methods for
  estimating reference evapotranspiration with missing data in
  Southern Ontario, Canada.* Agricultural Water Management 97:
  635–644. (Justifies "reduced-data PM" with assumed wind + Rs
  from T_max − T_min as preferable to HS.)
- **Widmer, N. (2024).** *Soil moisture and infiltration analysis
  of a swale system in Sadhana Forest.* M.Sc. thesis, ETH Zürich.
  §3.4 (PET methodology — Thornthwaite + Hargreaves).

---

## F. Topography (initial)

Two-pass memory-bounded streaming of the raw `.xyz` LiDAR scans
(`src/swale/xyz_streaming.py`, `scripts/13_xyz_inventory.py`) builds
an inventory of all 22 raw scans without loading any of them fully
into memory. After inventory we trimmed `data/DEM_xyz/` to 17 files
(5 dense `con_sw_and_for_*` + 12 task-specific).

A canonical map frame is defined once in `src/swale/spatial_frame.py`
(`+X = East, +Y = North, +Z = up`) and applied at load time by every
sensor / DEM / scan loader; no `ax.invert_*axis()` calls downstream.

The 5 dense scans are averaged into a single dense surface model
(`15_xyz_average_dense.py`, median per-bin Z std ≈ 1 mm), which feeds
the **hillshade base layer** (`src/swale/hillshade.py`).

Two views to present:
- `plots/12_dem_xy.png` — top-down `tripcolor` of `Mesh_swale_site.vtk`
  with 0.10 m contour lines and 0.50 m labelled majors.
- `plots/12_dem_3d.png` — PyVista oblique view, 2× vertical
  exaggeration, sensor pairs as coloured spheres.

This is initial topographic context, not a hydrologic result.

---

## G. Outlook — what's next

### G1. Spatial drill-down (still to work on)

`scripts/09_sensor_layout.py`, `10_per_location_vwc.py`,
`11_per_location_tau.py` already produce the per-location maps. The
per-location τ map (`plots/11_per_location_tau_map.png`) is the
hero figure showing the swale 40 cm slow drainage concentrates at
Bottom slope 1+2. Still open:
- Event-level drill-down at SMS07 / SMS09 vs SMS05 / SMS10 — which
  events drive the per-sensor τ spread?
- Resolve the SMS 6,7 vs 8,9 layout ambiguity.
- SMS02 follow-up (1 good fit at 40 cm — lower R² threshold or
  accept the data-poor caveat).

### G2. Tree-transpiration test (PET ↔ ΔVWC regression)

`scripts/07g_pet_dvwc_regression.py`. Daily mean VWC differenced to
get daily ΔVWC, joined with `08_pet_daily.csv`, filtered to the dry
window 2024-12-01 → 2025-04-30 (rain < 1 mm). Linear regression of
ΔVWC on PET at both raw daily and 7-day rolling-mean scales. The
slope β is the per-mm-PET water loss attributable to evaporative
demand; a steeper negative β at the swale sensor than at its control
twin indicates transpiration.

**Result.** The only sensor with a robust, scale-stable negative
coupling is **SMS07 (Bottom 1 swale, 40 cm)** — β ≈ −0.7 × 10⁻³
m³/m³ per mm-PET, daily R² 0.18 → 7-d R² 0.30. Its control twin
SMS16 sits at β ≈ 0. The Mound 40 cm (SMS05) hints at coupling
daily but washes out with smoothing. At 10 cm the *control*
sensors (SMS13, SMS15) couple to PET more strongly than the swale
sensors — consistent with the swale's vegetation canopy shading
the soil surface and suppressing direct evaporation while the trees
draw water from depth.

**Picture that emerges:** the swale's hydrologic effect is not
spatially uniform. The signature concentrates at the **Bottom slope
1+2** sensors — slow recession τ *and* clean transpiration coupling
both live at SMS07/SMS09. Trees at the foot of the slope are likely
the largest and most water-secure on the site.

### G3. Forward modelling with a Richards-equation solver

The recession-tail analysis is observational. The next phase is
**physics-based forward simulation** of the swale vs control profiles
using **LGAR-Py** (Layered Green-Ampt with Redistribution, a
Richards-equation-compatible vadose-zone model). Working setup notes
are in `notes/lgar_design_choices.md` and `config/lgar_setup.json`,
each input cited to the thesis section / equation / table it comes
from. The recession-tail derivation (Boussinesq / Richards basis for
exp vs power-law) is in `notes/recession_tail_richards.{tex,pdf}`.

The deliverable is matched observed vs simulated VWC at 10 cm and
40 cm for swale and control, using measured rainfall (gauge-valid
window only) + Hargreaves-Samani PET as forcing.
