# US Tree Map

A free, public-good web app: an animated 3D hex map of US tree history, climate fit and pest risk, six linked charts, and a species engine that ranks what to plant in each hex. Static-first. Pilot: one eastern state.

- Full plan: `docs/PLAN.md` (read the Corrections section and the current phase before planning work)
- Layout wireframe: `docs/img/layout.png`
- Look: Marco wants a clean, minimal, soft and rounded, editorial UI with muted blues; nothing rigid or corporate (`viz-style-guide` → UI chrome).
- Owner: Marco. He decides scope, the pilot state, data-contract changes and engine-rule changes.

## Status (update when a gate passes)

- Current phase: **0 · Setup**. Gate: mockup and data contract approved.
- Pilot state: **Wisconsin** (chosen Oct 27, 2026; see `docs/pilot-state.md`).

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
- **DuckDB 2.0** is current on PyPI. If `INSTALL h3 FROM community` fails on it, pin the newest 1.5.x release that has the `h3` extension and note it here.

## Layout

```
app/        web app (scaffolded in Phase 0)
pipeline/   data pipeline + tests (scaffolded in Phase 0)
data/       local inputs and outputs, gitignored (raw/, work/, out/)
docs/       PLAN.md, FIRST_PROMPT.md, img/, qa/ (gate evidence)
.claude/    skills/ (project rules), agents/reviewer.md, settings.json
```

## Commands

Fill in during Phase 0 and keep current.

- app: TBD (dev, test, build, lint, e2e)
- pipeline: TBD (env setup, run one layer, test)

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
