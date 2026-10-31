# US Tree Map

A free, public-good web app: an animated 3D hex map of US tree history, climate fit and pest risk, six linked charts, and a species engine that ranks what to plant in each hex. Static-first. Pilot: one eastern state.

- Full plan: `docs/PLAN.md` (read the Corrections section and the current phase before planning work)
- Layout wireframe: `docs/img/layout.png`
- Look: Marco wants a clean, minimal, soft and rounded, editorial UI with muted blues; nothing rigid or corporate (`viz-style-guide` → UI chrome).
- Owner: Marco. He decides scope, the pilot state, data-contract changes and engine-rule changes.

## Status (update when a gate passes)

- Current phase: **1 · Data pipeline** (plan approved by Marco). Steps 1–2 done Oct 28, 2026 (source checks; raster → hex engine). Step 3 (`hex_landcover`, `land_frac`) done Oct 29, 2026 on real data: 41 Annual NLCD 1.2 zips downloaded whole (54 GB in `data/raw/nlcd`; MRLC deflates the GeoTIFF, so range reads can't clip), build 321 s (P1 passes), fractions rounded to 0.1% by largest remainder (Marco, Oct 29) so the largest res-7 `p3` chunk is 585 kB (L5 passes; 2.2 MB unrounded). Step 4 (`hex_canopy`, TCC v2025-6) done Oct 28, 2026 on real data: 41 years clipped by range reads (4.4 GB in `data/raw/tcc/clip`), build 285 s (P1 one-layer ≤ 10 min passes), largest res-7 `p3` chunk 567 kB (L5 passes). The build machine has 8 GB RAM: keep reducer memory bounded (`raster.REDUCE_ROWS`, `REDUCE_THREADS`). Steps 5–6 (`hex_bps`, `hex_zone`) done Oct 29, 2026; `pipeline/mappings/bps_groups.csv` awaits Marco's review (18 of 42 rows flagged). Step 7 (`hex_trees`, TreeMap 2023) built Oct 31, 2026: 41 s, largest res-7 chunk 789 kB with values at 3 significant figures (2.2 MB unrounded), basal area within 0.001% of TreeMap's `BALIVE` (`docs/qa/treemap_balive.json`); the rounding and unknown-plot handling await Marco's OK before they go in the data contract. Gate: 20 random hexes spot-checked against the source maps (`docs/PLAN.md`). Oct 28: Marco switched to Annual NLCD 1.2 and TCC v2025-6; years run 1985–2025 (data contract D1, D2). IDS: 2021–2025 from the EDW map service for now (D5); retry the full IDS download (FHP pages returned 502 on Oct 27–28) before each build.
- Phase 0 · Setup: **done Oct 27, 2026.** Marco approved the mock (`docs/img/mock-v1.png`, route `/mock`) and the data contract (v1). Evidence: `docs/qa/phase0-smoke.md`.
- Pilot state: **Wisconsin** (chosen Oct 27, 2026; see `docs/pilot-state.md`).
- Decisions D1–D8 are made (data contract → Decisions); v0 numbers confirmed (`docs/numbers-v0.md`).
- Waiting on outside replies: Tree Equity Score permission (D7; draft in `docs/drafts/tes-permission-email.md`), NAPIS / Pest Tracker terms (not confirmed).
- Repo: https://github.com/mvrcotc/us-tree-map (public, MIT).
- Carried into later phases (reviewer, Oct 27, 2026): keyboard selection of hexes with a text readout (hard rule 5; Phase 2 gate), the selected hex's primary-ink outline (viz-style-guide → Selection; Phase 2), and the About panel with `catalog/sources.json` (hard rule 7; before any real data ships). The `ids` and `bps` checks were retried on Oct 28, 2026; results are in the data contract's Verified column.

## Hard rules

1. **Never invent data.** Every value on screen traces to a source in the `tree-map-data-contract` skill. Missing or not applicable → `null`, shown as "no data", never `0`.
2. **Pilot state only.** No areas outside Tree Atlas coverage (eastern US). The West waits for its own suitability model.
3. **Static-first.** v1 has no app server and no database: the pipeline writes Parquet, GeoJSON and JSON; the browser reads files. Cloudflare Workers and Supabase come after launch, and only if Marco asks.
4. **Screening tool, not advice.** Every ranked species shows its score parts, reasons and a confidence flag. Engine logic follows `species-engine-rules`; change that skill first, then code.
5. **Accessible by default.** Honor `prefers-reduced-motion`, keyboard access to every control, color never carries meaning alone, a table view for every chart (`viz-style-guide`).
6. **Budgets are gates.** `perf-budget` numbers must pass before a phase is called done.
7. **Licenses.** Keep the "not the official USDA map" disclaimer on hardiness-zone layers; credit every source in an About panel; don't ship a source whose license is unconfirmed in the data contract.
8. **No secrets** in the repo or the client bundle.

## Stack

- `app/`: React + TypeScript + Vite; a MapLibre GL JS street map (OpenFreeMap tiles) with a three.js 3D layer on top, through React Three Fiber, drei and `@react-three/postprocessing`, in a transparent canvas whose camera follows MapLibre's; hex columns as one `InstancedMesh` per H3 resolution; Apache ECharts; Zustand (one store); Tailwind + design tokens; Web Worker for the engine and chart aggregates; Vitest + Playwright.
- Browser data: Parquet over HTTP from R2, read with hyparquet in the Web Worker. DuckDB-Wasm is about 8.3 MB gzipped and fails the load budget (`perf-budget`).
- `pipeline/`: Python + DuckDB (`spatial`, `h3` community extension); raster reading with rasterio/pyproj; Earth Engine only if local processing is too slow.
- Hosting: Cloudflare Pages (app) + R2 (data). CI: GitHub Actions.
- v1 stage: zoomed out, the pilot state reads as a 3D diorama of hex columns over a faint map. Zoomed into a city, the street map and its labels come forward and the hexes become a translucent map layer under the labels. Terrain only in an optional landscape mode (`viz-style-guide` → Stage). Fallback if Phase 2's gate fails: deck.gl over MapLibre (`docs/PLAN.md`, corrections 10–11).

## Gotchas (checked Oct 27, 2026)

- **The project path has spaces** (`/Volumes/Backup One/Business/Code Projects/US Tree Map`, on an external drive). Quote every path in shell commands, npm scripts and Python; never build paths by string concatenation.
- **Pin three to 0.186.x.** postprocessing 6.39 supports three from 0.168 up to, but not including, 0.187. Upgrade three only after postprocessing widens that range.
- **Keep React on 19.3.x.** React Three Fiber 9.8 supports React 19.0 up to, but not including, 19.4.
- **Map + 3D layer sync (verified in a probe; follow it exactly):**
  - MapLibre owns the camera and all input. The three.js canvas sits on top with `pointer-events: none`, `gl={{ alpha: true }}`, a transparent clear color and `frameloop="never"`.
  - A MapLibre custom layer (`type: 'custom'`, `renderingMode: '3d'`) renders nothing itself. In `render(gl, args)` it updates the three.js camera, then calls React Three Fiber's `advance()`, so both layers draw in the same frame.
  - Local frame: meters around a fixed origin (x east, y up, z south). `M_local` = translate(origin as `MercatorCoordinate`) × scale(s, −s, s) × rotateX(90°), with s = `meterInMercatorCoordinateUnits()` at the origin.
  - Camera: `V = inverse(args.projectionMatrix) × args.defaultProjectionData.mainMatrix × M_local`; k = length of V's first column. Set `matrixWorldInverse = scale(1/k) × V` (view space in meters, which ambient occlusion needs), `matrixWorld` = its inverse, `projectionMatrix = args.projectionMatrix × scale(k)` and its inverse, `near = args.nearZ / k`, `far = args.farZ / k`. Turn `matrixAutoUpdate` and `matrixWorldAutoUpdate` off.
  - The probe measured 0 px error against `map.project` in four views, from top-down to street zoom.
- **three.js draws only when MapLibre does.** While a morph or other three.js animation runs, call `map.triggerRepaint()` each frame.
- **MapLibre GL JS 6 has no default export.** Use named imports: `import { Map, MercatorCoordinate, setWorkerUrl } from 'maplibre-gl'`. In a Vite build, call `setWorkerUrl(workerUrl)` with `import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'` before creating a map, or the built app fails with "Worker failed to load" (reproduced).
- **Never pass `essential: true`** to MapLibre camera calls: it overrides the visitor's reduced-motion setting.
- **Shadows:** three 0.186 removed `PCFSoftShadowMap`. A bare `<Canvas shadows>` asks for it and logs a fallback warning. Use `shadows="variance"` (soft) or `shadows="percentage"`. Column shadows reach the map through a `ShadowMaterial` plane at y = 0 in the three.js layer (verified).
- **Ambient occlusion:** the `SSAO` effect needs `<EffectComposer enableNormalPass>`.
- **Harmless warning:** with three 0.186, React Three Fiber 9.8 logs "THREE.Clock: This module has been deprecated" from its own code. Ignore it.
- **No React state in the frame loop.** Per-frame changes go through refs, shader uniforms and `useFrame`, never `setState` (`perf-budget` → Rendering rules).
- **TypeScript 7** (create-vite's default) works with the template's oxlint and type-checks this stack. Don't add typescript-eslint: its current release requires TypeScript below 6.1.
- **MapLibre's CSS sets `.maplibregl-map { position: relative }`**, which beats Tailwind's layered `absolute`: give the map container a sized wrapper (`h-full w-full` inside an `absolute inset-0` div) or it collapses to 0 px.
- **postprocessing's `NormalPass` swaps every mesh's material for a `MeshNormalMaterial`**, which ignores the column morph, so SSAO would see flat columns. `app/src/stage/Scene.tsx` sets `normalPass.renderPass.overrideMaterial` to the morph-aware normal material (`renderPass` is public but missing from the typings). The shadow pass gets the same morph through `mesh.customDepthMaterial`.
- **hyparquet's core reads only Snappy.** The data contract writes ZSTD, so pass `compressors: { ZSTD }` backed by `fzstd` (4.1 kB) to every `parquetRead*` call.
- **DuckDB 2.0 relations have no `fetchone()`**: use `con.execute(sql, params).fetchone()`, or `rel.limit(1).fetchall()`.
- **DuckDB 2.0** is current on PyPI. `INSTALL h3 FROM community` and `INSTALL spatial` both work on DuckDB 2.0.0 (checked Oct 27, 2026).

## Layout

```
app/        web app (scaffolded in Phase 0)
pipeline/   data pipeline + tests (scaffolded in Phase 0)
data/       local inputs and outputs, gitignored (raw/, work/, out/)
docs/       PLAN.md, FIRST_PROMPT.md, img/, qa/ (gate evidence)
.claude/    skills/ (project rules), agents/reviewer.md, settings.json
```

## Commands

App (`cd app`; Node 22, npm):

- `npm run dev`: dev server; serves `../data/out/` at `/data/`. `/mock` is the layout mock; `?test` installs `window.__stage` for e2e.
- `npm run typecheck` · `npm run lint` (oxlint) · `npm test` (Vitest)
- `npm run build`, then `npm run size`: bundle budgets L1/L2 (perf-budget)
- `npm run e2e`: Playwright against `vite preview` (builds first; ~10 min on software WebGL). Writes `docs/img/smoke.png` and `docs/img/mock-v1.png`. First time: `npx playwright install chromium`.

Pipeline (`cd pipeline`; Python 3.13 via uv, installed at `~/.local/bin/uv`):

- `uv sync`: create the environment
- `uv run treemap-pipeline [geo] [hex_base]`: run all steps or some; writes `data/out/v1/` and `docs/qa/pipeline-timing.json`
- `uv run pytest`

## How to work

- Start each phase and any multi-file task in plan mode. The plan names files, tests, and how the gate will be checked.
- One task at a time. Small commits with clear messages. Run tests and lint before saying a task is done.
- Look at UI changes before claiming them: run the app and take a Playwright screenshot.
- Before calling a phase done, check its gate in `docs/PLAN.md` and show the evidence (numbers, screenshots, spot-check table).
- If a source fact is uncertain, open the source; write "unverified" rather than guessing.
- Ask Marco before: adding a dependency over ~100 kB gzipped that isn't already in the Stack section, adding any paid service or account, changing the data contract, changing engine rules, or deleting data.
- Use the `reviewer` subagent after each task and before each gate.

## Models

- Default is Opus 5.5. `/model sonnet` for chart, UI and styling passes.
- Data-contract and engine-rule decisions: `/model fable` if your plan allows it (it may bill to usage credits), otherwise Opus with `/effort high`.

## Project skills (`.claude/skills/`)

- `tree-map-data-contract`: tables, columns, units, H3 resolutions, file paths, sources, licenses, open data decisions.
- `species-engine-rules`: gates, score components, weights, flags, reasons, confidence, required tests.
- `viz-style-guide`: validated color ramps, chart rules, number formats, motion timings, reduced motion.
- `perf-budget`: frame, update and load budgets and how to measure them.
