# App

React + TypeScript + Vite. A MapLibre street map owns the camera; a transparent three.js layer (React Three Fiber) draws the hex columns on top, synced from a MapLibre custom layer (`src/stage/mapSync.ts`, CLAUDE.md → Gotchas).

Commands are in CLAUDE.md → Commands. Layout:

- `src/stage/`: map, sync layer, hex columns (instanced, shader morphs), effects, test hooks
- `src/data/`: data worker (hyparquet + fzstd, h3-js) and synthetic Phase 0 values
- `src/theme/`: design tokens, ramps, muted basemap, palette tests
- `src/charts/`: ECharts panels, loaded after the first frame with hexes
- `src/mock/`: `/mock` layout for review
- `e2e/`: Playwright (alignment, true data colors, smoke, mock)
- `scripts/size.mjs`: bundle budgets (perf-budget L1, L2)

Phase 0 values on screen are synthetic and labeled so.
