# Phase 0 smoke screen: test evidence

**Gate passed Oct 27, 2026:** Marco approved the mock (`docs/img/mock-v1.png`) and the data contract.

Run Oct 27, 2026 (re-run after the reviewer fixes, all 6 e2e tests passing) on Marco's MacBook (Apple silicon), `npx playwright test` against the production build (`vite preview`), headless Chromium 156, viewport 1440 × 900 at DPR 1. Data: Wisconsin `hex_base` res 6 (4,037 hexes) with **synthetic** values. These runs check correctness only, never frame times (perf-budget → Reference setup).

| Check | Rule | Result |
| --- | --- | --- |
| Layer alignment vs `map.project`, 20 points per view | ≤ 1 px (perf-budget → Rendering rules) | top-down 0.000 px · 55° tilt 0.000 px · 70° tilt 0.000 px · street zoom (15.5) 0.000 px: **pass** |
| Column-top colors vs ramp, ~115 tops, grain and vignette off, top-down | OKLab ΔE × 100 ≤ 3 (viz-style-guide → True data colors) | worst 0.61 (first run); 1.01 after the muted basemap (`#015732` vs `#005a32`): **pass**. With the CSS vignette on, a top at the frame edge reached 3.54, so the test turns the overlay off |
| Smoke: map, columns, synthetic label, chart after first hex frame | — | pass; screenshot `docs/img/smoke.png` |
| Year slider → store → chart marker | — | pass |
| Click a hex (reduced motion) → selected, camera jumps to zoom 9.5 | viz-style-guide → Motion | pass |
| Vitest: store, Mercator frame, palette checks (ramps, colorblind separation, contrast) | viz-style-guide → How to check a palette change | 20 tests pass |
| Mock route renders every panel; need slider disabled (D7) | — | pass; screenshot `docs/img/mock-v1.png` |

## Bundle (perf-budget L1, L2; `npm run size`, gzip -9)

| File | kind | kB |
| --- | --- | --- |
| `index-*.js` (React, three.js, R3F, postprocessing, MapLibre main, app) | critical | 684.6 |
| `maplibre-gl-worker-*.mjs` | critical | 148.0 |
| `data.worker-*.js` (hyparquet, fzstd, h3-js) | critical | 82.8 |
| `YearPanel-*.js` (ECharts, loaded after the first hex frame) | lazy | 172.0 |
| `MockPage-*.js` (`/mock` only) | lazy | 3.3 |
| **L1 critical path** | budget 1,100 | **915.4: pass** |
| **L2 all JS without user action** | budget 1,300 | **1,090.8: pass** |
