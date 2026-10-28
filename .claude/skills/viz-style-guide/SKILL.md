---
name: viz-style-guide
description: Visual and motion rules for the US Tree Map. Use before choosing any color, building or changing the stage (street map, three.js layer, lighting, effects, columns, city view, terrain, camera), a chart, legend, tooltip, number format or animation, and when reviewing UI for accessibility. Gives the UI chrome and stage art direction, the true-data-color rule, checked color ramps per metric, chart rules, number formats, motion timings and reduced-motion behavior.
---

# Visual and motion style guide (v0)

Phase 0's design system may re-skin these, but any replacement ramp must pass the same checks (bottom of this file) before use.

## UI chrome (panels, controls, type)

Marco's direction: clean, minimal, soft and rounded, editorial; muted blues; nothing rigid or corporate. Phase 0 turns this into tokens in `app/src/theme/` and a mock for his approval.

- **Surfaces:** a soft off-white page; panels with 12–16 px radii, soft low-contrast shadows, hairline dividers and generous padding. No heavy borders or hard boxes.
- **Type:** an editorial serif for panel titles and headline numbers; a quiet sans for controls, labels and tooltips; tabular figures wherever numbers line up.
- **Accent:** one muted blue, for interactive state only: focus ring, selected tab, active toggle, slider. It never appears on the map or in a chart, so it can't be read as data (planting need keeps its own Blues ramp).
- **Controls:** pill toggles and segmented controls, round slider thumbs, and a focus ring with at least 3:1 contrast against its background.
- **Motion:** calm and eased, with no bounce or spring overshoot. Timings are under Motion.

## Stage (street map + three.js layer)

The goal is the most visually captivating view that still reads accurately. A MapLibre street map sits underneath; three.js draws the hex layer on top, in a transparent canvas whose camera follows MapLibre's (CLAUDE.md → Gotchas). Zoomed out, the pilot state reads as a diorama and the columns are the subject. Zoomed in, the streets are.

- **Projection:** Web Mercator, MapLibre's, so the hexes line up with the streets at every zoom. Northern hexes look slightly larger (about 8% across Pennsylvania); tooltips and charts carry exact values. Analysis stays in the pipeline.
- **Street map:** OpenFreeMap's Positron style, muted further toward the UI palette (soft roads and water, light labels) so data colors stay dominant. The attribution stays visible.
- **Zoomed out (state view):** the map is faint (most layers hidden or at low opacity) with the state outline and county lines from `geo/`.
- **Zoomed into a city** (the zoom where street names become readable, set in Phase 2): the map comes forward. The columns sink and fade out while the same hexes fade in as a translucent MapLibre fill layer under the map's labels, so street names stay crisp on top.
- **Columns mode (default):** a flat base, so heights compare fairly; height and color both encode the metric.
- **Landscape mode (optional):** MapLibre terrain from DEM tiles, with its vertical exaggeration stated in the legend ("relief ×N"). Hexes drape over it as a fill, not columns.
- **Light:** one warm key light from the northwest (the cartographic convention), a cool sky fill, soft shadows. A shadow-only ground plane lays column shadows over the map. Ambient occlusion only deepens the gaps between columns.
- **True data colors:** column tops render the exact ramp color: unlit, with no tone mapping applied to the data. Shading lives on the column sides. A Playwright test samples the center of rendered top faces (grain off) and fails if any differs from its ramp color by more than 3 (OKLab ΔE × 100). In the city view the hex fill is translucent, so its colors blend with the map; the legend, tooltips and charts carry exact values there.
- **Effects:**
  - Bloom only on selected and highlighted hexes, with a threshold above every ramp color.
  - Ambient occlusion and bloom apply to the hex layer only.
  - Vignette (darkness ≤ 0.35, frame edge only) and grain (≤ 3% opacity) are one CSS overlay above both layers, so the map and the hexes get the same treatment.
  - No depth of field: it would blur the hex layer but not the map.
  - The Low tier turns every effect off with no loss of meaning (`perf-budget` → Rendering rules).
- **Selection:** the selected hex gets a primary-ink outline, a 4% lift and the highlight bloom. Other hexes keep their colors.
- **Intro:** on first load the columns rise from the ground in a west-to-east wave, then the camera settles (timings under Motion).
- **Trees (Phase 4, optional):** close to a selected hex, low-poly procedural trees for its top-ranked species grow on it: generic conifer or broadleaf silhouettes sized by mature-height class, labeled as generic. Never present them as what a species looks like.

## Map metric ramps

One metric shows at a time; each has its own hue family so switching metrics never reuses a meaning. Hex values are ColorBrewer schemes: import them from `d3-scale-chromatic` (it ships ColorBrewer's license) rather than retyping. Height and color both encode the metric.

| Metric | Type | Ramp (low → high) |
| --- | --- | --- |
| Canopy change since 1985 | Diverging, 0 at the gray midpoint | `schemeBrBG[7]`: loss `#8c510a #d8b365 #f6e8c3` · no change `#f5f5f5` · gain `#c7eae5 #5ab4ac #01665e` |
| Habitat change by 2100 | Diverging | `schemePuOr[7]` reversed so decrease is orange: decrease `#b35806 #f1a340 #fee0b6` · `#f7f7f7` · increase `#d8daeb #998ec3 #542788` |
| Pest pressure | Sequential | `schemeOranges[7]` steps 2–7: `#fdd0a2 #fdae6b #fd8d3c #f16913 #d94801 #8c2d04` |
| Planting need | Sequential | `schemeBlues[7]` steps 2–7: `#c6dbef #9ecae1 #6baed6 #4292c6 #2171b5 #084594` |
| Best-species score | Sequential | `schemeGreens[7]` steps 2–7: `#c7e9c0 #a1d99b #74c476 #41ab5d #238b45 #005a32` |

- Diverging height uses the absolute value; color carries the sign. The legend states the sign in words ("loss", "gain").
- No data: not extruded, hairline outline only, and the legend has a "no data" swatch. Never color no-data as the low end.
- Classes: 6 quantized classes per sequential metric (7 for diverging) with fixed breaks per metric, not per view, so colors mean the same thing everywhere. Breaks are documented in `app/src/theme/`.
- Checked Oct 27, 2026 (OKLCH): every ramp above reads light → dark monotonically, stays in one hue family per arm, and keeps ≥ 0.06 lightness between steps. Their lightest steps fall below 2:1 contrast on a light surface by design (near zero recedes), so never use a ramp's lightest step for a labeled tier. Re-check all ramps if the stage's ground goes dark.

## Chart categories (land cover, past vs. now)

| Entity | Light | Dark |
| --- | --- | --- |
| Forest | `#008300` | `#008300` |
| Grass / pasture | `#eda100` | `#c98500` |
| Cropland | `#6250d6` | `#9085e9` |
| Developed | `#e34948` | `#e66767` |
| Other | `#898781` (muted ink) | `#898781` |

Stack order bottom → top: forest, grass/pasture, cropland, developed, other. Colors follow the entity everywhere, never its rank. Checked Oct 27, 2026 in this order: light mode passes adjacent-pair colorblind separation (worst ΔE 16.2) and normal-vision separation (worst 30.3), but yellow is under 3:1 contrast; dark mode passes, with yellow↔green colorblind separation in the 6–8 warning band. Both results make **direct labels and 2 px gaps between stacked fills mandatory** for these charts.

## Chart rules (ECharts)

- One y-axis per chart. Two measures → two charts.
- Two or more series → a legend; four or fewer → also direct-label them.
- Text (labels, values, legends) uses text colors, never the series color: primary `#0b0b0b`, secondary `#52514e`, muted `#898781` on light.
- Thin marks: 2 px lines, ≥ 8 px dots, 2 px gaps between adjacent fills, hairline gridlines.
- Every chart has a hover tooltip and a "Show as table" toggle.
- Selection: the selected item keeps full color with a primary-ink outline; the rest drop to 35% opacity. Hover on a chart mark highlights matching hexes on the map.
- Species score bars: one stacked bar per species, segments = weighted components in fixed order native, climate, pest, need, using `#2a78d6`, `#eb6834`, `#1baf7a`, `#eda100` (a set checked for adjacent-pair separation). Score number at the bar end in text color.
- Pest heat grid: Oranges ramp; every cell also prints its severity number.
- Climate dumbbell: "now" dot in secondary ink, "2100" dot in the habitat-change ramp's end color for its direction, 2 px connector.
- Need vs. canopy scatter: one color; at most three colored groups (larger sets fail all-pairs separation).
- Confidence and status: icon plus label (high, medium, low), never color alone.

## Number formats

- Shares: `42%`. Changes in shares: signed percentage points, one decimal: `+3.4 pts`.
- Area: acres in the UI with thousands separators (`12,400 acres`), km² in tooltips. Data stays metric.
- Hardiness: zone label (`6b`) and °F range.
- Scores: integer 0–100. Severity: `8/10`.
- Species: common name first, scientific name in italics.
- Years: plain (`1985`); projection labels say the period: "2070–2099".
- Every panel footer: "Source: {name}, {version}" linking to the source.

## Motion

| Change | Duration | Easing | How |
| --- | --- | --- | --- |
| Year step (hexes) | 600 ms | ease-in-out cubic | shader uniform `t` between per-instance `from` and `to` (`perf-budget` → Rendering rules) |
| Metric change | 800 ms | ease-in-out cubic | same |
| Intro rise (first load) | 1,200 ms total; 600 ms per column, staggered west → east | ease-out cubic | per-instance delay attribute |
| Chart update | 500 ms | `cubicInOut` | ECharts `animationDurationUpdate`, `animationEasingUpdate` |
| Fly to clicked hex | ~1,500 ms | MapLibre's default curve | MapLibre `flyTo`, pitch about 50° |
| City-view handoff (columns ↔ fill) | 600 ms | ease-in-out cubic | columns sink via the morph uniform while the MapLibre fill's opacity rises |
| Panel enter / exit | 200 / 150 ms | ease-out / ease-in | CSS or GSAP |
| Hover highlight | instant | — | |

- Play mode advances one year every 900 ms (600 ms morph + 300 ms hold) and pauses on any user input.
- One camera move at a time; nothing loops.
- **Reduced motion** (`prefers-reduced-motion: reduce`): all durations 0; `jumpTo` instead of `flyTo` and `easeTo`; no intro rise (columns appear at full height); ECharts `animation: false`; the guided tour advances only on click; play mode steps without morphing. Never pass `essential: true` to MapLibre camera calls; it overrides the viewer's setting.

## How to check a palette change

Write these as unit tests next to the theme code:

- Sequential and diverging arms: OKLCH lightness strictly monotonic, ≥ 0.06 between steps, one hue family per arm.
- Categorical sets: OKLab ΔE × 100 between adjacent entries ≥ 8 under simulated protanopia and deuteranopia (Machado et al. 2009, severity 1.0); 6–8 only with direct labels or gaps; ≥ 15 for normal vision.
- Contrast against the chart surface ≥ 3:1, or the chart must ship direct labels or a table view.
