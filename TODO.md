# TODO

## 2026-05-08

- [ ] **Rain gauge inspection** (logger 19570). Silent from 2025-06-22 22:15 onward; data flow healthy, values pegged at 0.0. Likely mechanical jam or disconnected lead. Until repaired, all rain-driven analysis is bounded above by 2025-06-22.
- [ ] Look for older XLSX snapshots that extend XLSX coverage of loggers 05511 and 19570 past Feb 2025 — if found, ingest them and re-evaluate whether the bulk_ec / saturation-extract-EC aliasing is still acceptable.
- [ ] Apply the per-sensor first-week (or first-fortnight) cutoff to drop sensor-equilibration data before analysis. Decide cadence per channel: day 0–3 is unusable across the board; soil_temp clean by ~day 2; EC on a few control sensors keeps drifting through ~day 12.
- [ ] Decide what to do with SMS10 (`Location='Step??'`, treatment derived from explicit column = swale, depth = 40 cm). Currently included in 40 cm swale analysis as a 5th sensor; user count of "4 swale at 40 cm" suggests it may not be intended as a swale comparison sensor. Either rename location, set treatment to null, or accept inclusion.
- [ ] Decide whether to keep SMS23 / SMS24 (`Location = ?`) — currently excluded (null treatment + null depth).
- [ ] Drill into the **40 cm treatment difference**: control 40 cm sits at 0.30–0.45 m³/m³, swale 40 cm at 0.05–0.10. Hypothesise mechanism (mound geometry, lateral flow, soil profile difference) and test against more events.
- [ ] Event-based drydown analysis: pick a subset of events from `plots/rain_events.csv`, fit exponential decay to the post-rain recession at each depth × treatment, compare drydown timescales.
- [ ] Optional follow-up on time-frequency: swale-minus-control difference TFRs to highlight where the treatments diverge in frequency-time. (Spectrograms alone aren't very discriminating between treatments per current view.)
- [ ] Optional: discrete Haar (DWT) decomposition for sharp-transition characterisation. The current `mexh` CWT covers most of this need; DWT would only be worth it if dyadic-scale energy partitioning becomes useful.

## Done in this session

- [x] Time-frequency phase started: scipy & MNE Welch PSD, Morlet/mexh/cmor TFR, multi-sensor spectrogram per depth, TFR caching, event-window time-domain plot.
- [x] Control depths populated in metadata; cache refreshed; metadata parser updated for new `tag` and `treatment` columns and the Dataloggers subtable column shift.
- [x] Detected and tabulated 84 rain events (`plots/rain_events.csv`).
- [x] Confirmed rain-gauge failure post 2025-06-22 (documented in Issues).

## Issues

- [issue] `bulk_ec` step jump of 1.7–3.3 mS/cm at ~2025-02-04 on loggers 05511 + 19570 is a source-switch artifact (Bulk EC vs Saturation Extract EC aliased). Diagnostic in `plots/diag_bulk_ec.png` and `plots/boundary_report.csv`. Fix deferred — see `memory/bulk_ec_source_artifact.md`.
- [issue] Rain gauge on logger 19570 reports continuous 0 mm from 2025-07 onward through 2026-02 (~8 months) despite ~8928 rows/month being logged at 5-min cadence. 2024-08 had 323 mm; 2025-08 has 0 mm. Almost certainly a physical fault (clogged tipping bucket, stuck mechanism, or detached lead). Action: have the gauge inspected on-site; meanwhile any analysis that relies on rain forcing is restricted to ≤ 2025-06.
