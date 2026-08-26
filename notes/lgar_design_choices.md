# LGAR-Py reproduction of Widmer (2024) — design choices

This document is the prose companion to `config/lgar_setup.json`. Every
parameter and methodological decision is traced to a specific page,
section, equation or table of Widmer's MSc thesis
(`notes/Masters_thesis_Neomi_Widmer_18-115-303-1.pdf`). Items that the
thesis does not pin down explicitly are flagged so they remain visible
when we iterate.

The goal is **closed-loop reproducibility** with Widmer's numerical work
before going further (HYDRUS-1D comparison or otherwise).

---

## 1. Why LGAR first, then HYDRUS

Widmer chose LGAR-Py over Richards-equation solvers (HYDRUS) for these
reasons, stated in §3.5 (p. 24):

- "Physically based" but cheap relative to Richards.
- Required parameters can be derived from soil physical properties
  (we have those from her 27 texture samples and 18 bulk-density
  samples).
- Implicit solution → computationally efficient.
- The LGAR-Py paper (La Follette et al. 2023) reports "highly
  agreeing model predictions" with HYDRUS-1D in semi-arid conditions.

Widmer's LGAR runs failed to reproduce the observed VWC dynamics
(§3.5.2, pp. 28–29), in particular the slow buildup at 40 cm. The user
has reasonably asked whether HYDRUS would do better — but the simpler
falsification is to **first reproduce Widmer's LGAR result**, then ask
whether the failure modes she documented are intrinsic to the LGAR
formulation or to her parameter / configuration choices. Only after
that is the LGAR-vs-HYDRUS comparison meaningful.

## 2. LGAR-Py: which version

`pip` does not currently package LGAR-Py. Three known sources upstream:

| version | url | maintained? |
|---|---|---|
| Publication snapshot (Python) | <https://www.hydroshare.org/resource/90951d952b034e7aa592898ab6d264eb/> | no |
| Python/torch fork | <https://github.com/NWC-CUAHSI-Summer-Institute/LGAR-py> | partial |
| LGAR-C / LASAM (current) | <https://github.com/NOAA-OWP/LGAR-C> | yes (C; no Python wrapper) |

**Choice**: the HydroShare publication snapshot, vendored into this
repo at `external/lgar_py/` once we begin. This is the version Widmer
would have used given her thesis date (2024). The C version is the
correct choice for production but breaks the
"reproduce Widmer exactly" goal of this first phase.

## 3. PET methodology

**Method**: Hargreaves-Samani (1982). Penman-Monteith is the FAO
standard but requires wind speed; the ATMOS 14 station at logger 19570
does not record wind. Widmer §3.4 (p. 23).

**Formulas** (Widmer Eq. 3–7, p. 23):
- `PET = 0.0023 * (Tmax − Tmin)^0.5 * (Tmean + 17.8) * Ra` [mm/day]
- `Ra = (24·60/π) · G_sc · d_r · [ω_s·sin(φ)·sin(δ) + cos(φ)·cos(δ)·sin(ω_s)]`
- `d_r = 1 + 0.033·cos(2π·J/365)`
- `δ = 0.409·sin(2π·J/365 − 1.39)`
- `ω_s = arccos(−tan(φ)·tan(δ))`

**Constants and inputs**:
- Solar constant `G_sc = 0.82 MJ/m²/day` (Widmer §3.4, p. 23; Abbot 1963; FAO 1998).
- Latitude `φ = 1.9807°` ⇒ in rad. Widmer §2.3.1 (p. 7).
- `Tmax`, `Tmin`, `Tmean`: daily aggregates of `air_temp` from logger 19570
  port 5 (ATMOS 14).
- `J`: Julian day of year (1–365).

**Output cadence**: daily PET (Widmer Fig. 12, p. 21, plots daily
cumulative PET as bars). The LGAR model itself integrates sub-daily;
we'll distribute daily PET across daylight hours uniformly (one
plausible choice — Widmer doesn't specify the disaggregation).

### Two units fixes applied vs Widmer §3.4

Reproducing Widmer's Eq. 3–7 verbatim gives a PET ~12 mm/day, which is
not physical for the tropics (literature: 3–7 mm/day for southern
India). Two unit-convention errors in the thesis explain the
discrepancy; both are documented inline in
`scripts/08_pet_hargreaves.py` and applied here.

1. **Solar constant**. Widmer's text gives `G_sc = 0.82 MJ/m²/day`,
   but the (24·60/π) prefactor in Eq. 4 expects `G_sc` in MJ/m²/min.
   Standard FAO value `G_sc = 0.0820 MJ/m²/min` is used here. Without
   this fix, `Ra` would be a factor 1440 too small.
2. **`Ra` units in Hargreaves PET formula**. Widmer's Eq. 3 has `Ra` in
   `MJ/m²/day` but the conventional Hargreaves-Samani / FAO-56 form
   uses `Ra` in water-equivalent mm/day. Conversion is
   `Ra_mm = Ra_MJ / λ` with `λ = 2.45 MJ/kg` (Allen et al. 1998
   Eq. 20). Without this fix PET is ~2.45× too high.

After both fixes the daily-mean PET over our record is **4.88 mm/day**,
in line with tropical Hargreaves-Samani norms. Widmer's Thornthwaite
citation (`§2.3.1`, p. 7) of 2.3 mm/day comes from a different method
known to under-estimate PET in tropical climates and is not directly
comparable to a Hargreaves-Samani output. Hargreaves-Samani is
Widmer's own choice for the modelling step.

## 4. Soil texture classification

(Widmer §3.5.1, p. 27)

- 27 samples collected at electrode positions 1, 5, 10 on every ER line,
  both plots.
- Sedimentation analysis by Auroville Environmental Monitoring Services
  (EMS SOIL 2000, Stokes' law).
- Majority of AEMS samples returned **Silt Loam**.
- The project soil scientist and prior site work (Roeschli et al. 2021)
  classified the soil as **Sandy Clay Loam**.
- **Compromise used: Loam**.

Reasoning given: "the significant influence of soil texture on the
determination of model parameters" required reconciliation; Loam
covers the disagreement.

Implication: the van Genuchten parameter ranges are LOAM ranges, not
Silt Loam, not Sandy Clay Loam. We follow that.

## 5. van Genuchten / Mualem parameter ranges

(Widmer Tables 4–5, p. 28)

| symbol | unit | min | max | mean | source |
|---|---|---|---|---|---|
| θ_r | – | 0.120 | 0.354 | 0.238 | min observed VWC at 10 cm (Table 4) |
| θ_s | – | 0.379 | 0.464 | 0.422 | 1 − ρ_b/ρ_s from 18 samples (Eq. 17, Table 4) |
| K_s | mm/h | 0.827 | 19.289 | 5.060 | SoilKsatDB (Gupta et al. 2021), Loam |
| α_vG | 1/mm | 3.8e-5 | 4.5e-4 | 2.5e-4 | Bohne et al. 1995, Loam (Table 5) |
| n_vG | – | 1.142 | 1.229 | 1.186 | Bohne et al. 1995, Loam (Table 5) |
| m_vG | – | 0.124 | 0.186 | 0.155 | m = 1 − 1/n (Mualem closure) |
| l    | – | – | – | 0.5 | Mualem default per La Follette 2023 |

Notes:

- Widmer's α ≈ 0.0025 /cm and n ≈ 1.19 are characteristic of fine-
  textured / clay-rich loam — *not* the generic loam textbook value
  (n ≈ 1.5). This matters because n controls the steepness of the
  retention curve.
- ρ_b (oven-dry, 105 °C, cylindrical samples) per Poeplau et al. 2017.
  ρ_s gravimetric per Santos et al. 2022.
- θ_r at 40 cm (observed range 0.268–0.411 m³/m³, Table 4) is **not**
  used as θ_r by Widmer; the 10 cm minimum is.

## 6. AET reduction (Šimůnek et al. 2013 form)

Widmer §3.5 (p. 27), Eq. 16:

```
AET = PET · 1 / (1 + (ψ / ψ_50)^3)
```

- `ψ_50 = 0.75 m` (Widmer §3.5, p. 27).
- AET demand drawn from the topmost wetting front per LGAR-Py
  default (La Follette et al. 2023).
- No surface ponding modelled. Widmer reasoning: "as the simulated
  site is sloping water accumulating on the surface for a longer time
  is not expected" (p. 27). Site slope = 5 % (§2.3.4, p. 9).

## 7. Calibration recipe to follow (and not to repeat)

Widmer's calibration narrative (§3.5.2, pp. 28–29):

1. Forward run with mean parameter values from Tables 4–5 → poor fit.
2. 10 000 random samples within (min, max) ranges → poor fit.
3. `scipy.optimize.minimize` (Nelder-Mead) → no improvement.
4. Per LGAR-Py developer: log-space sampling of K_s and α; variable
   initial capillary head; PySwarms particle-swarm minimisation →
   no improvement.
5. Smooth rainfall input from 5-min → 1-hour intervals → marginal.
6. Manual AET / PET ratio tweaks → no improvement.

Diagnostic failure modes (Widmer p. 29):

- Modeled peaks **narrower** than observed.
- Modeled VWC returns to baseline **too fast**.
- Slow buildup at 40 cm **not reproduced** by the model.

Our plan:

- Re-run step 1 first with our larger dataset and confirm we hit the
  same wall.
- Document the discrepancy quantitatively (RMSE, NSE per depth × event)
  rather than presenting a single event.
- Only then consider what changes might rescue LGAR (e.g. two layers
  with a near-saturated bottom layer mimicking the perched zone),
  before declaring the formulation inadequate.

## 8. Sensor mapping caveat

Widmer's Table 6 (p. 32) numbers sensors 1–16 with explicit
(side, location, depth) assignments. Our `Metadata.xlsx` numbers them
SMS01–SMS16 but the mapping may not match one-for-one — sensor
positions on the slope might have been re-keyed during commissioning,
and the metadata's `tag` column has its own location labels
(`slope`, `mount`, `step`, `down`, `far`, …) that don't obviously
correspond to Widmer's location names (`Top slope`, `Step`, `Mound`,
`Bottom slope 1/2`).

**Before any comparison run** we'll resolve the mapping by joining on
(treatment, depth, descriptive label) and surface any unresolved
ambiguities.

## 9. What Widmer leaves us to decide

Not in the thesis but needed to run the model:

- **Column depth and bottom BC**. Widmer doesn't state. LGAR-Py demo
  uses ~2 m. Water table is at ~1.8 m b.g.l. (§1 intro, p. 2; from
  Sadhana Forest's documented reforestation effect raising the table
  from 8 m to 1.8 m).
- **Sub-daily PET disaggregation**. Daily PET → hourly PET by
  uniformly distributing across daylight hours.
- **Initial VWC profile** at t = 0 of the run.
- **Swale-vs-control parameterisation**. Same VGM parameters with
  different forcing? Or different parameters per plot? Widmer
  effectively uses one parameter set across both.
- **Layering**. Widmer treats the column as homogeneous. The site
  could plausibly have a finer-textured horizon at depth (Cuddalore
  → Manaveli transition). Two-layer LGAR is supported but would
  introduce more free parameters than we can constrain.

All of these are encoded as `TODO` or as open questions in
`config/lgar_setup.json`.

## 10. Comparison with HYDRUS-1D

Deferred until we have a working LGAR baseline. The LGAR-vs-HYDRUS
question is: does the failure to reproduce the 40 cm buildup come
from (a) the Green-Ampt piston-flow assumption (which would be fixed
by Richards in HYDRUS) or (b) the homogeneous-column assumption
(which both formulations share)? If LGAR runs at our hand reproduce
Widmer's failure modes, we already know answer (a) is at least part
of the story. If LGAR with a perched-bottom-BC reproduces the data,
we have an alternative explanation that doesn't require HYDRUS.

## Sources

- [LGAR-Py publication snapshot (HydroShare)](https://www.hydroshare.org/resource/90951d952b034e7aa592898ab6d264eb/)
- [LGAR-Py Python/torch fork](https://github.com/NWC-CUAHSI-Summer-Institute/LGAR-py)
- [LGAR-C / LASAM (current C version)](https://github.com/NOAA-OWP/LGAR-C)
- [La Follette et al. 2023, *Water Resources Research*](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2022WR033742)
- Widmer, N. (2024). MSc thesis, ETH Zurich. Local: `notes/Masters_thesis_Neomi_Widmer_18-115-303-1.pdf`.

## Next steps

1. **Verify sensor mapping** (Widmer Table 6 ↔ our SMS01–16) — small
   script reading Metadata.xlsx and producing a one-to-one map or
   flagging discrepancies.
2. **Implement Hargreaves-Samani PET** (`scripts/08_pet_hargreaves.py`),
   outputting `plots/08_pet_daily.{csv,png}` with rainfall overlay.
   Compare seasonality qualitatively against Widmer Fig. 12.
3. **Vendor LGAR-Py** from the HydroShare snapshot into
   `external/lgar_py/` and write a thin wrapper that consumes
   `config/lgar_setup.json`.
4. **Forward run with mean parameters** on one event, both plots,
   replicate Widmer Fig. 14.
5. **Quantitative misfit report**: RMSE, NSE per (event, sensor) for
   the full record (not just Widmer's 8 events).
6. Decide: tune LGAR further (layered, perched BC) or move to HYDRUS.
