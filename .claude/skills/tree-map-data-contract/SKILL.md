---
name: tree-map-data-contract
description: The US Tree Map data contract. Use before writing or changing pipeline code, any Parquet, GeoJSON or JSON output, or app code that reads them, and when adding or verifying a data source. Defines every hex table, column, type, unit, H3 resolution, file path, null rule, the raster-to-hex method, and the source, version and license behind each field.
---

# US Tree Map data contract (v0 draft)

Status: drafted from planning, sources checked Oct 27, 2026. Phase 0 confirms each source's current version, access method and license (fill the Verified column), resolves the open decisions at the bottom, and Marco approves. After that this file is the law: code follows it, and every change starts here.

## Global rules

- **Hex ids:** H3 v4. Store as `UBIGINT` in Parquet. Convert to the 15-character hex string (`BigInt.toString(16)`) only where h3-js or app code needs it.
- **Resolutions shipped:** 5, 6, 7 for the pilot state. Resolution 8 is the pipeline's working grid and is published only for metro detail later.
- **Every hex table** has `h3 UBIGINT`, `res TINYINT`, `p3 UBIGINT` (resolution-3 parent, the partition key and the Tree Atlas join key).
- **Units in data:** fractions 0–1, km², SI, except where the source unit is the user-facing unit (°F hardiness zones, ft²/acre basal area). The UI converts (see `viz-style-guide`).
- **Nulls:** missing or not applicable → `NULL`. Never `0`. Tables built from rasters carry `valid_frac` (share of the hex with valid source pixels).
- **Years:** `SMALLINT`. Scenarios: `'rcp45' | 'rcp85'`.
- **Parquet:** ZSTD, sorted by `h3` (then `year`), row groups of at most 100k rows.
- **Provenance:** every value's source is listed in `catalog/sources.json`; the app's About panel reads it.

## Sources

| id | Source | Version and coverage | Used for | License / terms | Verified |
| --- | --- | --- | --- | --- | --- |
| `bps` | LANDFIRE Biophysical Settings | Latest LF release (record version). Modeled pre-Euro-American-settlement vegetation potential, not observed history | Past vegetation | US federal product; confirm terms on landfire.gov | — |
| `nlcd` | Annual NLCD Collection 1.1 Land Cover (USGS) | 1985–2024, 16 classes, CONUS, released 2025-06-25 | Land-cover shares per year | US federal (USGS); confirm citation | Years and classes 2026-10-27 |
| `tcc` | USFS Tree Canopy Cover, NLCD TCC | v2023.5: annual 1985–2023, 30 m, CONUS. Earth Engine lists a newer 2025-6 version | Canopy % per year | "Can be used without additional permissions or fees"; cite USDA Forest Service | 2026-10-27 |
| `treemap` | TreeMap 2023 CONUS (RDS-2026-0038) | Circa 2023, 30 m, forested pixels only; raster of imputed FIA plot ids + tree-list CSV | Current species composition | "Can be used without additional permissions or fees"; cite the publication | 2026-10-27 |
| `phzm` | 2023 USDA Plant Hardiness Zone Map GIS data (PRISM, Oregon State) | 1991–2020 data, about 800 m | Hardiness zone | Altered or derived maps must say "not the official USDA map" and drop USDA/OSU logos | Earlier session |
| `atlas` | DISTRIB-II habitat suitability, Climate Change Tree Atlas v4 (RDS-2019-0029) | 125 eastern species; baseline 1981–2010; future 2070–2099 only; CCSM4, GFDL CM3, HadGEM2-ES × RCP 4.5/8.5; 10 km / 20 km hybrid lattice; shapefiles | Climate fit | "Can be used without additional permissions or fees"; cite Peters et al. 2019 (dataset and Ecology and Evolution paper) | 2026-10-27 |
| `potter` | Potter et al. 2019, Forests 10(4):304, Table S1 | 419 native hosts, 339 agents, 1,378 host–agent pairs, severity 1–10 | Pest–host severity | CC BY 3.0 | 2026-10-27 |
| `ids` | USFS Insect and Disease Survey (IDS) | Annual aerial/ground damage polygons | Pest activity near a hex | Confirm terms and service URL | — |
| `napis` | NAPIS Pest Tracker (CERIS, Purdue) | County survey status for exotic pests | Exotic pest presence | Confirm terms and download method | — |
| `plants` | USDA PLANTS | Native status by state; traits | Native component, traits | Confirm access method and which trait fields exist | — |
| `fia_ref` | FIA REF_SPECIES (FIA DataMart) | Current | SPCD ↔ PLANTS symbol, genus | US federal | — |
| `census` | US Census Bureau cartographic boundary files (states, counties) | Latest vintage (record it) | `state_fips`, `county_fips`, pilot-state clip, county-level pest joins, state outline and county lines on the map | US government work; confirm on census.gov | — |
| `basemap` | OpenFreeMap vector tiles and styles (OpenStreetMap data via OpenMapTiles) | Hosted service; Positron style | Street map, street names, place labels | Free, no key, no request limits, commercial use allowed; attribution required (MapLibre shows it automatically with OpenFreeMap styles) | 2026-10-27 |
| `dem` | USGS 3D Elevation Program (3DEP) seamless DEM, 1 arc-second | Current (record the date) | `elev_m`, landscape-mode relief | US government work; confirm on usgs.gov | — |
| `tes` | Tree Equity Score (American Forests) | National; ~200,000 urban neighborhoods | Planting need (urban) | Not stated on the site ("All Rights Reserved" footer). Get written OK before publishing derived values | 2026-10-27 |

Never treat Tree Atlas values as per-hex facts: the Atlas asks for summaries over at least 8,000 km². See `atlas_r3`.

## Tables

Types are DuckDB/Parquet types. All hex tables also have `h3`, `res`, `p3`.

### `hex_base` (static)
| column | type | meaning |
| --- | --- | --- |
| `area_km2` | FLOAT | H3 cell area |
| `state_fips` | VARCHAR | majority state |
| `county_fips` | VARCHAR | majority county (5 digits) |
| `land_frac` | FLOAT | non-water share (latest NLCD year) |
| `in_atlas` | BOOLEAN | hex center inside Tree Atlas model coverage |
| `elev_m` | FLOAT | mean elevation in meters (`dem`); used by landscape mode |

### `hex_bps` (static, LANDFIRE)
| column | type | meaning |
| --- | --- | --- |
| `bps_forest_frac` | FLOAT | share whose BpS group is forest or woodland |
| `bps_savanna_frac` | FLOAT | share in savanna groups |
| `bps_open_frac` | FLOAT | share in grassland or shrubland groups |
| `bps_wetland_frac` | FLOAT | share in non-forested wetland groups |
| `bps_other_frac` | FLOAT | everything else (barren, water, sparse) |
| `bps_top_code`, `bps_top_name` | INTEGER, VARCHAR | most common BpS in the hex |
| `valid_frac` | FLOAT | |

BpS code → group mapping lives in `pipeline/mappings/bps_groups.csv` (one row per code, with the LANDFIRE vegetation-group attribute it came from). Marco reviews it in Phase 1.

### `hex_landcover` (one row per hex per year, 1985–2024, Annual NLCD)
Fractions of valid pixels; they sum to 1 (± 1e-6).
| column | NLCD classes |
| --- | --- |
| `frac_forest` | 41, 42, 43 |
| `frac_woody_wetland` | 90 |
| `frac_developed` | 21, 22, 23, 24 |
| `frac_crop` | 82 |
| `frac_grass_pasture` | 71, 81 |
| `frac_shrub` | 52 |
| `frac_herb_wetland` | 95 |
| `frac_water` | 11 |
| `frac_barren` | 31 |
| `frac_snow` | 12 |
| `valid_frac` | |

Chart groups (UI): Forest = forest + woody wetland; Grass/pasture; Cropland; Developed; Other = the rest.

### `hex_canopy` (one row per hex per year, 1985–2023, USFS TCC)
| column | type | meaning |
| --- | --- | --- |
| `canopy_frac` | FLOAT | mean tree canopy over valid pixels (TCC % / 100) |
| `valid_frac` | FLOAT | |

Metric "canopy change since 1985" = `canopy_frac(year) − canopy_frac(1985)`, computed in the app.

### `hex_trees` (one row per hex per species present, TreeMap 2023)
| column | type | meaning |
| --- | --- | --- |
| `spcd` | SMALLINT | FIA species code |
| `ba_ft2ac` | FLOAT | live basal area per acre, averaged over the hex's forested pixels |
| `ba_share` | FLOAT | species share of the hex's live basal area |
| `tpa` | FLOAT | live trees per acre |
| `forest_px_frac` | FLOAT | share of hex pixels that TreeMap maps as forest |

Live trees only. Basal area per tree (ft²) = 0.005454 × DBH² (inches), times trees per acre. Confirm tree-list field names against the CSV in Phase 1.

### `hex_zone` (static, PHZM 2023)
| column | type | meaning |
| --- | --- | --- |
| `zone_coldest` | VARCHAR | coldest half-zone in the hex, e.g. `'6a'` |
| `zone_coldest_num` | FLOAT | numeric half-zone: 6a = 6.0, 6b = 6.5 |
| `zone_mode` | VARCHAR | most common half-zone |
| `valid_frac` | FLOAT | |

The engine gates on the coldest half-zone (conservative).

### `atlas_r3` (one row per res-3 cell × species × scenario × GCM)
| column | type | meaning |
| --- | --- | --- |
| `p3` | UBIGINT | resolution-3 cell (~12,400 km² average) |
| `spcd` | SMALLINT | |
| `scenario` | VARCHAR | `'rcp45'` or `'rcp85'` |
| `gcm` | VARCHAR | `'ccsm4'`, `'gfdl_cm3'`, `'hadgem2_es'` or `'mean'` (mean of the three) |
| `iv_cur` | FLOAT | modeled importance value, 1981–2010, area-weighted over the pool |
| `iv_fut` | FLOAT | modeled importance value, 2070–2099 |
| `ratio` | FLOAT | `iv_fut / iv_cur`; NULL when `iv_cur = 0` |
| `change_class` | VARCHAR | `'increase'` (> +20%), `'no_change'` (within ±20%), `'decrease'` (< −20%), `'new'` (`iv_cur = 0`, `iv_fut > 0`), `'absent'` |
| `reliability` | VARCHAR | Atlas model reliability: `'high'`, `'medium'` or `'low'` (confirm where it is published) |
| `pool_km2` | FLOAT | area summarized |
| `pooled` | BOOLEAN | true if neighbors were added to reach 8,000 km² |

Pooling: assign Atlas lattice cells to a res-3 cell by centroid. If the pool covers less than 8,000 km² (coast, state edge), add neighboring res-3 cells (`grid_disk` k = 1) until it does, and set `pooled = true`.

### `hex_pests` (one row per hex × agent with known status)
| column | type | meaning |
| --- | --- | --- |
| `agent_id` | VARCHAR | id in `catalog/pests.json` |
| `source` | VARCHAR | `'ids'` or `'napis'` |
| `level` | VARCHAR | `'hex'` (IDS polygons) or `'county'` (NAPIS) |
| `status` | VARCHAR | `'present'` or `'surveyed_absent'`; no row = unknown |
| `first_year`, `last_year` | SMALLINT | years detected within the window |
| `damage_frac` | FLOAT | IDS only: share of hex inside mapped damage, over the window; NULL for county-level rows |

### `hex_need` (static, urban only)
| column | type | meaning |
| --- | --- | --- |
| `tes` | FLOAT | Tree Equity Score 0–100, area-weighted over neighborhoods in the hex |
| `tes_canopy_frac` | FLOAT | TES canopy share, area-weighted |
| `tes_cover_frac` | FLOAT | share of the hex covered by TES neighborhoods |
| `need` | FLOAT | `1 − tes/100` when `tes_cover_frac ≥ 0.5`, else NULL |

## Catalogs (JSON)

- `species.json`: `spcd`, `plants_symbol`, `sci_name`, `common_name`, `genus`, `family`, `native_l48`, `native_states[]`, `in_atlas`, `atlas_reliability`, `min_zone_num` + `min_zone_source`, `mature_height_ft` + source, `size_class` (`large` ≥ 50 ft, `medium` 30–50, `small` < 30).
- `pests.json`: `agent_id`, `common_name`, `sci_name`, `kind` (insect, disease, plant), `origin` (native, nonnative), `hosts[]` of `{spcd, severity}` from Potter Table S1, `ids_codes[]`, `napis_names[]`.
- `sources.json`: `id`, `name`, `publisher`, `version`, `url`, `terms`, `citation`, `accessed`.
- `bps_groups.json`: BpS code → group, with a `reviewed` flag.

## Files and paths

- Local: `data/raw/{source_id}/` (downloads, never edited), `data/work/` (intermediates), `data/out/v{N}/` (publishable).
- Published on R2: a mirror of `data/out/v{N}/`.
  - Hex tables: `v{N}/hex/{table}/r{res}/{p3}.parquet` (`{p3}` = 15-character hex string)
  - Catalogs: `v{N}/catalog/{name}.json`
  - Map overlays: `v{N}/geo/{name}.json`: pilot-state outline and county lines as simplified GeoJSON (EPSG:4326)
  - Terrain for landscape mode: DEM tiles MapLibre can read, built from `dem` (format decided when landscape mode is built)
  - `v{N}/manifest.json`: for every file, table, res, rows, bytes, sha256, source ids, created_at.
- Bump `N` for any breaking change. Never overwrite a published version.

## Raster → hex method

1. Clip each 30 m raster to the pilot state plus a 10 km buffer, so edge hexes are whole.
2. Transform each pixel center to EPSG:4326 (pyproj, `always_xy=True`) and index it to its resolution-8 cell. Do this once per source grid and clip window, vectorized, and cache the cell index in `data/work/` for every year of that source (`perf-budget` → Pipeline rules).
3. Per cell, count pixels per class (categorical) or sum values and valid pixels (continuous).
4. Roll up to resolutions 7, 6, 5 with `cell_to_parent`, summing counts and sums. Compute fractions and means last; never average child fractions.
5. Polygon sources (TES, IDS, counties): area-weighted overlay in EPSG:5070 at resolution 8, then roll up the same way.

## Checks (pipeline tests)

- Land-cover fractions sum to 1 per hex-year.
- Roll-up consistency: parent pixel counts equal the sum of child counts.
- No negative values; fractions within 0–1; years within each source's range.
- Row counts and value ranges written to the manifest.
- Phase 1 gate: `pipeline/qa/spot_check.py` samples 20 random res-7 hexes (fixed seed) and writes `docs/qa/phase1_spotcheck.csv` (hex, layer, our value, source value, match, note) for Marco to check against the source viewers.

## Decisions (made by Marco, Oct 27, 2026)

- D1. **No 2050 step.** The time control runs pre-settlement → 1985 … 2024 → 2070–2099. A mid-century source can be added later as its own layer.
- D2. **Canopy: NLCD TCC** (`tcc`). The slider runs to 2024; at 2024 the canopy layer shows its 2023 values with a visible "latest: 2023" badge in the legend, tooltip and chart. The same rule applies to any layer whose years end before the slider's year: show its latest earlier year, always labeled with that year.
- D3. **Candidates: the 125 Tree Atlas species only** for v1. Urban species without projections wait until after launch.
- D4. **Need outside TES coverage is NULL** (not applicable). The engine skips the need component there without lowering confidence (`species-engine-rules` → Step 6).
- D5. **Pests:** IDS uses the last 10 survey years; "nearby" means the hex or its res-6 ring of neighbors (`grid_disk` k = 1, about 10 km). NAPIS stays county-level. `hex_pests` rows from IDS carry `level = 'hex'` and already include the ring.
- D6. **Species hardiness:** USDA PLANTS "Temperature, Minimum (°F)" converted to a half-zone; where missing, the coldest PHZM half-zone among FIA/TreeMap plots recording the species. `min_zone_source` is `'plants'` or `'fia_range'`.
- D7. **Tree Equity Score: hold until written OK.** Marco emails American Forests. Until permission arrives in writing, the pipeline may build `hex_need` locally but never publishes it, and public builds hide the need layer and weight (need is NULL everywhere).
- D8. **Savanna is its own class.** `bps_savanna_frac` counts toward neither open nor forest. It drives the `RESTORE_SAVANNA` hex flag (`species-engine-rules` → Step 1).
