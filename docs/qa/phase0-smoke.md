# Phase 0 smoke screen: test evidence

Run Oct 27, 2026 on Marco's MacBook (Apple silicon), `npx playwright test` against the production build (`vite preview`), headless Chromium 156, viewport 1440 × 900 at DPR 1. Data: Wisconsin `hex_base` res 6 (4,037 hexes) with **synthetic** values. These runs check correctness only, never frame times (perf-budget → Reference setup).

| Check | Rule | Result |
| --- | --- | --- |
| Layer alignment vs `map.project`, 20 points per view | ≤ 1 px (perf-budget → Rendering rules) | top-down 0.000 px · 55° tilt 0.000 px · 70° tilt 0.000 px · street zoom (15.5) 0.000 px: **pass** |
| Column-top colors vs ramp, 120 tops, grain off, top-down | OKLab ΔE × 100 ≤ 3 (viz-style-guide → True data colors) | worst 0.61 (`#228944` vs `#238b45`): **pass** |
| Smoke: map, columns, synthetic label, chart after first hex frame | — | pass; screenshot `docs/img/smoke.png` |
| Year slider → store → chart marker | — | pass |
| Click a hex (reduced motion) → selected, camera jumps to zoom 9.5 | viz-style-guide → Motion | pass |
| Vitest: store, Mercator frame | — | 8 tests pass |

## Bundle (perf-budget L1, L2; `npm run size`, gzip -9)

| File | kind | kB |
| --- | --- | --- |
| `index-*.js` (React, three.js, R3F, postprocessing, MapLibre main, app) | critical | 683.3 |
| `maplibre-gl-worker-*.mjs` | critical | 148.0 |
| `data.worker-*.js` (hyparquet, fzstd, h3-js) | critical | 82.8 |
| `YearPanel-*.js` (ECharts, loaded after the first hex frame) | lazy | 172.0 |
| **L1 critical path** | budget 1,100 | **914.1: pass** |
| **L2 all JS without user action** | budget 1,300 | **1,086.1: pass** |
