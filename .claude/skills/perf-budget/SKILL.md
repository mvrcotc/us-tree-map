---
name: perf-budget
description: Performance budgets for the US Tree Map and how to measure them. Use before adding a dependency, loading data in the browser, changing the street map, the three.js layer, their camera sync, shaders, effects, quality tiers, transitions, the Web Worker or chart updates, writing pipeline steps that touch rasters, and before calling Phase 1, 2, 3 or 4 done. Gives frame, update, load, bundle, data and pipeline budgets, the reference device, the rendering rules behind them, and how each number is measured.
---

# Performance budget (v0)

Status: v0 numbers set Oct 27, 2026 from measured probe builds (see Baseline); confirmed by Marco on Oct 27, 2026 (`docs/numbers-v0.md`). A phase isn't done until its rows pass on the reference device, with results saved in `docs/qa/`. Raise a budget only with Marco's OK, and write the reason here.

## Reference setup

- **Device:** Marco's MacBook Air (Apple silicon), plugged in, Chrome stable, window 1440×900, no other tabs.
- **Quality tier:** frame budgets (F rows) are measured at the High tier on the reference device. Lower tiers exist for weaker hardware, not to pass a gate.
- **CI** (GitHub Actions, headless Chromium with software WebGL) checks bundle size, data size, rendered colors and logic timing only. Never use CI frame times: the three.js probe drew 0.4 frames per second in headless Chromium with software WebGL.
- **Data:** gate runs use real pipeline output for the pilot state. Synthetic fixtures are fine while building.

## Budgets

| id | What | Budget | Gate |
| --- | --- | --- | --- |
| F1 | Frame time, whole pilot state at res 6, scripted 10 s orbit | median ≤ 16.7 ms, p95 ≤ 25 ms | Phase 2 |
| F2 | Same, one region at res 7 | median ≤ 16.7 ms, p95 ≤ 25 ms | Phase 2 |
| F3 | Year-step morph (600 ms), 10 steps | p95 ≤ 33 ms; no main-thread long task > 50 ms | Phase 2 |
| F4 | Hover → hex highlight and tooltip visible | p95 ≤ 50 ms | Phase 2 |
| F5 | Quality fallback | When p95 stays above 25 ms for 2 s, drop one tier; never oscillate more than once per 10 s | Phase 2 |
| U1 | Control change (year, metric, scenario, weight slider, hex selection) → every chart panel and the species list show new values | p95 ≤ 100 ms over 20 changes per control | Phase 3 |
| U1b | Weight or scenario change → the stage's best-species metric updated (debounced 100 ms per `species-engine-rules`) | p95 ≤ 250 ms | Phase 3 |
| U2 | Worker round trip for one hex's ranking (post → result received) | p95 ≤ 20 ms | Phase 3 |
| U3 | Best-species score for every hex of the pilot state at res 7, in the worker | ≤ 80 ms | Phase 3 |
| L1 | Critical-path JS (everything needed to draw the first hexes, MapLibre included), gzip | ≤ 1,100 kB | Phase 4 |
| L2 | All JS loaded without user action (critical path + charts loaded after the first frame), gzip | ≤ 1,300 kB | Phase 4 |
| L3 | First-view data (`hex_base` + default metric, all years, res 6, outlines), compressed transfer; street-map tiles excluded | ≤ 1.5 MB | Phase 4 |
| L4 | Navigation → first frame with hexes, cold cache | ≤ 3 s unthrottled; ≤ 6 s at 9 Mbps down, 1.5 Mbps up, 60 ms RTT, 4× CPU slowdown | Phase 4 |
| L5 | One zoom-in chunk (one table, one `p3` partition, res 7, all years), compressed | ≤ 1 MB | Phase 1 |
| M1 | Hex instances drawn at once | ≤ 60,000 | Always |
| P1 | Full pilot-state pipeline rebuild on the reference device, downloads excluded | ≤ 60 min; one layer ≤ 10 min | Phase 1 |

kB = 1,000 bytes, matching Vite's build report.

## Baseline (measured Oct 27, 2026)

Probe builds: Vite 8.3.5, production mode, each emitted JS file compressed with `gzip -9`.

| Package (version) | Imported | gzip |
| --- | --- | --- |
| react + react-dom (19.3.1) | `createRoot` | 67.7 kB |
| react + three (0.186.1) + @react-three/fiber (9.8.2) | `Canvas`, a lit mesh | 305.5 kB (three + R3F ≈ 238 kB) |
| + @react-three/drei (10.7.9) | `CameraControls`, `ContactShadows` (the stage now needs only `PerformanceMonitor`) | +11.8 kB |
| + @react-three/postprocessing (3.2.2) with postprocessing (6.39.5) | `EffectComposer` + seven effects (the stage now uses `SSAO`, `Bloom`, `SMAA`) | +89.4 kB |
| maplibre-gl (6.16.0) | `Map`, `MercatorCoordinate`, `setWorkerUrl`, worker via `?url` | 429.1 kB (main 282.2 + worker 146.9) |
| h3-js (4.5.0) | `latLngToCell`, `cellToBoundary` | 62.2 kB |
| zustand (5.0.16) | `create` | 1.4 kB |
| echarts (6.1.0) | core; bar, line, scatter, heatmap, custom; grid, tooltip, legend, brush, dataset; canvas renderer | 199.5 kB |
| hyparquet (1.31.5) | `parquetReadObjects` | 17.1 kB |
| @duckdb/duckdb-wasm (1.33.1-dev57.0), EH build | JS + worker + wasm | ≈ 8.3 MB before any extension |
| Fallback, not used: deck.gl (9.4.0) core + layers + geo-layers + maplibre, incl. h3-js | `MapLibreOverlay`, `H3HexagonLayer` | 308.8 kB |

The stage as designed (overlay probe: React, three.js, React Three Fiber, `SSAO` + `Bloom` + `SMAA`, MapLibre with its worker, h3-js, Zustand): **883.7 kB** (main chunk 736.8 + MapLibre worker 146.9). For comparison, three.js without the street map was 477.1 kB, and the deck.gl + MapLibre probe was about 811 kB without ECharts.

What follows from it:

- **MapLibre loads up front:** it runs the camera for both layers.
- **Load ECharts after the first frame with hexes** (dynamic `import()`, tree-shaken modules). That leaves about 890 kB of libraries on the critical path, with room for app code under L1.
- **Browser Parquet reader: hyparquet in the Web Worker**, with aggregates as typed-array loops. DuckDB-Wasm can't meet L1–L4; it would need Marco's OK and load only on demand.
- **Every new dependency:** measure it the same way and add a row here before adopting it.

## Rendering rules

- **One `InstancedMesh` per H3 resolution, one draw call.** Instances keep one order (sorted by `h3`) and one count across years and metrics, so per-instance attributes line up. Geometry: a six-sided prism with its base at y = 0, per-instance scale and rotation from the cell's projected boundary, drawn at about 94% size so hairline gaps separate the columns.
- **Morphs run in the vertex shader.** Per-instance `from` and `to` attributes (height value, color) plus one uniform `t` animated 0 → 1. On a new year or metric, copy the current interpolated values into `from`, write the new `to`, reset `t`; an interrupted morph never jumps. Upload only the attributes that changed (`needsUpdate`).
- **No React state in the frame loop.** Per-frame work goes through refs, uniforms and `useFrame`. React re-renders only when a control changes.
- **three.js draws inside MapLibre's frame.** `frameloop="never"`; the sync layer calls `advance()` from MapLibre's `render` (CLAUDE.md → Gotchas). MapLibre renders only when something changes, so an idle page costs nothing. During morphs and other three.js animations, call `map.triggerRepaint()` each frame.
- **Quality tiers:**
  - **High:** ambient occlusion (`SSAO`), soft shadows (`shadows="variance"`) on the shadow-only ground plane, bloom for highlights, SMAA, CSS grain; device pixel ratio up to 2.
  - **Medium:** no ambient occlusion; ratio up to 1.5.
  - **Low:** no post-processing, no shadows; ratio 1.
  - Choose with drei `PerformanceMonitor` (F5), let the viewer override it in settings, and start phones at Low.
- **Effects never change what the data says.** Follow `viz-style-guide` → Stage (true data colors, effects at the edges and for highlights only).
- **Picking:** MapLibre receives all pointer input (the three.js canvas has `pointer-events: none`). For hover and click, raycast the instanced mesh with a three.js `Raycaster` from the synced camera at the pointer position, at most once per frame. In the city view, use the event's `lngLat` → `latLngToCell`. If hover shows up in profiles (F4), switch to GPU picking.
- **Alignment is tested.** A Playwright test draws a three.js marker at known points and compares its position with `map.project` at four camera angles (top-down, 55°, 70°, street zoom); it fails above 1 px. It can run in CI: software WebGL is slow but exact.
- **Level of detail by zoom:** res 6 for the whole state, res 7 for a region (load the `p3` partitions in view), never more than M1 instances.
- **WebGL2 is required.** Check once at startup and fall back to the flat 2D mode.
- **One update per frame.** Coalesce store changes into at most one stage update and one chart update per animation frame. The worker answers each request once; no streaming partial results into React.

## Pipeline rules

- A state at 30 m is on the order of 10⁸ pixels per layer-year. Vectorize pixel → cell; never loop over pixels in Python. Options: DuckDB's `h3` extension (`h3_latlng_to_cell`, `h3_cell_to_parent`) over arrays, or another vectorized H3 library.
- Compute each pixel's res-8 cell once per source grid and clip window, cache it in `data/work/`, and reuse it for every year of that source (Annual NLCD has 40). Reuse it across sources only after checking that CRS, transform and window match exactly.
- Read rasters by block window with bounded memory; never hold a whole state × all years in RAM.
- Before downloading a source, check its file sizes and any clip-to-area download option, and tell Marco the disk space needed.

## How to measure

- **Frames and hover (F1–F5):** `app/e2e/perf.spec.ts`, run headed on the reference device. It opens `/?perf=1` (a route that skips the tour and exposes `window.__perf`), drives MapLibre's camera (`easeTo`, `rotateTo`), steps years, and records frame deltas from `useFrame`, long tasks (`PerformanceObserver` type `longtask`), the active quality tier, and `gl.info.render` (draw calls, triangles). It writes `docs/qa/perf-<phase>-<yyyy-mm-dd>.json`.
- **Update latency (U1–U3):** the control handler calls `performance.mark('input:<control>')`; each chart panel marks `paint:<panel>` in the first `requestAnimationFrame` after it applies new data; the stage marks `paint:stage` in the first `useFrame` after its attributes upload. U1 = last paint mark − input mark, 20 changes per control, report p50 and p95. The worker reports its own compute time for U2 and U3.
- **Bundle (L1, L2):** build with `build.manifest: true`; `app/scripts/size.mjs` gzips (level 9) every emitted JS file and sums critical-path vs. lazy chunks from the manifest. Runs in CI and fails over budget.
- **Data (L3, L5):** read sizes from `data/out/v{N}/manifest.json`; CI fails over budget.
- **Load time (L4):** Playwright with a CDP session: `Network.emulateNetworkConditions` (download 9 Mbps, upload 1.5 Mbps, latency 60 ms), `Emulation.setCPUThrottlingRate` (rate 4), cold cache, navigation start → `paint:stage` with hex instances drawn.
- **Pipeline (P1):** the pipeline's run-all entry point times each step and writes `docs/qa/pipeline-timing.json`.
- **Log:** every gate run appends a row to `docs/qa/perf-log.md`: date, commit, device, tier, each id's result vs. budget.

## When a budget fails

Profile before changing code: Chrome's Performance panel, `gl.info.render`, the worker's timings. Turn effects off one at a time to find the expensive one. Fix the cause, then re-measure.
