# Pipeline

Python 3.13 + uv. Builds the pilot state's hex tables, outlines and catalogs per `.claude/skills/tree-map-data-contract/SKILL.md`.

```bash
cd pipeline
uv sync                         # create .venv from uv.lock
uv run treemap-pipeline         # run every step (downloads raw inputs on first run)
uv run treemap-pipeline geo     # one step: geo, hex_base
uv run pytest                   # tests
```

Outputs: `data/raw/{source}/` (downloads), `data/work/` (res-8 working grid), `data/out/v1/` (publishable: `hex/`, `geo/`, `manifest.json`). Step timings go to `docs/qa/pipeline-timing.json`.

Built so far: `hex_base` (`h3`, `res`, `p3`, `area_km2`; other columns NULL until their sources land) at res 5–8, and `geo/state.json` + `geo/counties.json` from Census cartographic boundaries (2025 vintage).
