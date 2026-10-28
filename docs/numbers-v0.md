# v0 numbers for confirmation

Every v0 number from `species-engine-rules` and `perf-budget`, in one place (Phase 0, step 5). Marco confirms or changes them here; the skills are then updated to match and this file records the outcome.

Status: **confirmed by Marco, Oct 27, 2026, as written.**

## Species engine (`species-engine-rules`)

| # | Rule | v0 value |
| --- | --- | --- |
| E1 | `RESTORE_OPEN`: historical open share | `bps_open_frac` ≥ 0.5 |
| E2 | `RESTORE_OPEN` / `RESTORE_SAVANNA`: max developed share | `frac_developed` < 0.3 |
| E3 | `RESTORE_SAVANNA`: historical savanna share | `bps_savanna_frac` ≥ 0.5 |
| E4 | `REFOREST`: historical forest share | `bps_forest_frac` ≥ 0.5 |
| E5 | `REFOREST`: canopy drop since 1985 | ≥ 0.15 (15 points) |
| E6 | Tree Atlas minimum summary area (pooling) | 8,000 km² (set by the Atlas) |
| E7 | G2 lethal pest: severity | ≥ 9 of 10 |
| E8 | G3 habitat collapse: future/current ratio | < 0.5 (mean of 3 GCMs) |
| E9 | Change class bands | increase > +20%; no change ±20%; decrease < −20% |
| E10 | Climate component by class | increase 1.0 · no change 0.75 · decrease 0.35 · new 0.6 |
| E11 | GCM disagreement penalty | × 0.8 |
| E12 | Native component | state 1.0 · lower 48 0.6 · otherwise 0 |
| E13 | Need size factor | large 1.0 · medium 0.7 · small 0.4 |
| E14 | Size classes (mature height) | large ≥ 50 ft · medium 30–50 ft · small < 30 ft |
| E15 | Need from TES | `1 − tes/100` when `tes_cover_frac` ≥ 0.5 |
| E16 | Diversity modifier (10-20-30 rule) | × 0.85 if species > 10%, genus > 20% or family > 30% of basal area |
| E17 | Default weights | native 1 · climate 1 · pest 1 · need 1 |
| E18 | Weight sliders | 0–2, step 0.25 |
| E19 | Species shown | top 15 |
| E20 | Reason chips per species | at most 4 |
| E21 | Confidence | start high; −1 level per issue; 2+ drops → low |
| E22 | Best-species metric recompute debounce | 100 ms |
| E23 | Pest window and "nearby" (D5) | IDS last 10 survey years; hex + res-6 ring (k = 1) |

## Performance (`perf-budget`)

| id | What | v0 budget |
| --- | --- | --- |
| F1 | Frame time, whole state at res 6, 10 s orbit | median ≤ 16.7 ms, p95 ≤ 25 ms |
| F2 | Same, one region at res 7 | median ≤ 16.7 ms, p95 ≤ 25 ms |
| F3 | Year-step morph, 10 steps | p95 ≤ 33 ms; no long task > 50 ms |
| F4 | Hover → highlight + tooltip | p95 ≤ 50 ms |
| F5 | Quality fallback | drop a tier when p95 > 25 ms for 2 s; at most once per 10 s |
| U1 | Control change → all panels updated | p95 ≤ 100 ms (20 changes per control) |
| U1b | Weight/scenario → stage best-species metric | p95 ≤ 250 ms |
| U2 | Worker round trip, one hex ranking | p95 ≤ 20 ms |
| U3 | Best-species score, every res-7 hex in the state | ≤ 80 ms |
| L1 | Critical-path JS, gzip | ≤ 1,100 kB |
| L2 | All JS loaded without user action, gzip | ≤ 1,300 kB |
| L3 | First-view data, compressed | ≤ 1.5 MB |
| L4 | Navigation → first frame with hexes, cold | ≤ 3 s unthrottled; ≤ 6 s throttled (9/1.5 Mbps, 60 ms, 4× CPU) |
| L5 | One zoom-in chunk (res 7, one `p3`, all years) | ≤ 1 MB |
| M1 | Hex instances drawn at once | ≤ 60,000 |
| P1 | Full pipeline rebuild (no downloads) | ≤ 60 min; one layer ≤ 10 min |
| Q1 | Device pixel ratio by tier | High ≤ 2 · Medium ≤ 1.5 · Low 1 |
| Q2 | Alignment test tolerance | ≤ 1 px vs. `map.project` |
| Q3 | True-data-color tolerance (`viz-style-guide`) | OKLab ΔE × 100 ≤ 3 |

For scale: the shipped Wisconsin grid has 4,037 hexes at res 6 and 27,304 at res 7 (`docs/pilot-state.md`), so the whole state at res 7 still fits M1.
