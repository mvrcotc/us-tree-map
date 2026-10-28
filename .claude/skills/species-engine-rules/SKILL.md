---
name: species-engine-rules
description: How the US Tree Map species engine ranks trees for a hex. Use before writing or changing the engine, its Web Worker, the species panel, the best-species map metric, or engine tests. Covers hex flags, eligibility gates, the four score components (native, climate fit, pest safety, need), weights, the diversity modifier, reasons, confidence, output types and required tests.
---

# Species engine rules (v0 draft)

Status: v0 thresholds confirmed by Marco on Oct 27, 2026 (`docs/numbers-v0.md`), with decisions D3–D8 applied. From now on, change this file first, then the code. The engine is a screening tool: it narrows choices and explains each one. The UI says so next to the list.

## Inputs

From `tree-map-data-contract`: `hex_base`, `hex_bps`, `hex_landcover` and `hex_canopy` (latest year, plus 1985), `hex_trees`, `hex_zone`, `atlas_r3` (via the hex's `p3`), `hex_pests`, `hex_need`, `catalog/species.json`, `catalog/pests.json`. From the store: `scenario` (`'rcp45'` or `'rcp85'`) and `weights`.

Candidates (v1): the 125 Tree Atlas species (decision D3). Urban species without projections wait until after launch.

## Step 1: hex flags (shown above the list)

| flag | condition (v0) | message |
| --- | --- | --- |
| `RESTORE_OPEN` | `bps_open_frac ≥ 0.5` and `frac_developed < 0.3` | Historically prairie or shrubland. Native grassland restoration may fit better than planting trees. The tree list collapses behind "Show trees anyway". |
| `REFOREST` | `bps_forest_frac ≥ 0.5` and canopy fell by ≥ 0.15 since 1985 | Lost forest canopy since 1985: reforestation candidate. |
| `RESTORE_SAVANNA` | `bps_savanna_frac ≥ 0.5` and `frac_developed < 0.3` | Historically oak savanna: widely spaced native oaks with prairie beneath. The tree list stays visible. |
| `NO_ATLAS` | `in_atlas` is false | No climate projection here. Climate component is skipped; confidence is capped at low. |
| `SMALL_SAMPLE` | `atlas_r3.pooled` is true | Climate fit pooled with neighboring areas. |

Savanna counts toward neither `RESTORE_OPEN` nor `REFOREST` (decision D8).

## Step 2: gates (remove a species, keep the reason for "Why not X?")

| gate | condition (v0) | reason shown |
| --- | --- | --- |
| G1 hardiness | species `min_zone_num` > hex `zone_coldest_num` | Not cold-hardy here (zone {z}). |
| G2 lethal pest | an agent with `status = 'present'` nearby: an IDS row for the hex (which already covers its res-6 ring of neighbors and the last 10 survey years, decision D5) or a NAPIS row for its county has Potter severity ≥ 9 on this species | {pest} is present nearby; severity {s}/10. |
| G3 habitat collapse | `atlas_r3` ratio < 0.5 for the scenario (mean of 3 GCMs) | Suitable habitat projected to fall by more than half by 2100. |
| G4 no habitat | `change_class = 'absent'` for the scenario | No suitable habitat now or by 2100. |

Potter severity scale (Potter et al. 2019): 10 near-complete mortality of mature hosts; 9 near-complete mortality in a congeneric host; 8 significant mortality (~25–95%); 5 moderate (~10–25%); 3 moderate with other stressors (~1–10%); 1 minor (< ~1%).

## Step 3: components (each 0–1, or null when there's no data)

- **native**: 1.0 if native to the pilot state (PLANTS), 0.6 if native to the lower 48 but not this state, 0 otherwise.
- **climate**: from `atlas_r3` for the hex's `p3`, chosen scenario, `gcm = 'mean'`:
  - `increase` 1.0 · `no_change` 0.75 · `decrease` 0.35 · `new` 0.6 plus reason "New habitat by 2100: assisted-migration candidate"
  - If the three GCMs disagree on direction (some ratio > 1, some < 1), multiply by 0.8 and add the downgrade below.
  - Null when `NO_ATLAS` or the species isn't modeled.
- **pest**: `1 − max(severity)/10` over agents with `status = 'present'` that list this species as a host; 1.0 when none. Unknown pest status is not "absent": if the county has no survey rows, add the downgrade below.
- **need**: hex `need` × size factor (`large` 1.0, `medium` 0.7, `small` 0.4). Null when `need` is null: outside Tree Equity Score coverage that means not applicable (decision D4). In public builds need is null everywhere until American Forests gives permission (decision D7), and the need slider is hidden.

## Step 4: score

- `score = round(100 × Σ wₖ·cₖ / Σ wₖ)`, summing only components that are not null (weights renormalize).
- Then multiply by the **diversity modifier**: 0.85 if, in `hex_trees`, the species is above 10% of basal area, its genus above 20%, or its family above 30% (the 10-20-30 guideline, Santamour 1990); otherwise 1.0.
- Default weights: native 1, climate 1, pest 1, need 1. Sliders run 0–2 in steps of 0.25. All zero → show "Set at least one weight".
- Ties: higher climate, then higher pest, then scientific name A–Z.
- Show the top 15. Gated species are listed under "Why not…?" with their gate reason.

## Step 5: reasons

At most four chips per species, ordered by weighted contribution. Each chip has `code`, plain-language `text`, and `source` id. Examples:

- "Native to {state}" (`plants`)
- "Habitat holds or grows by 2100 under {scenario}" / "Habitat shrinks by more than 20% by 2100" (`atlas`)
- "{pest} nearby: severity {s}/10" (`potter`, `ids` or `napis`)
- "Large shade tree for a high-need neighborhood" (`tes`, `plants`)
- "Already {x}% of basal area here" (`treemap`)

## Step 6: confidence (label plus icon, never color alone)

Start at high. Drop one level for each: Atlas reliability `low`; GCMs disagree on direction; `pooled`; pest survey status unknown for the county; need is null while the need weight is above 0 and the hex has `tes_cover_frac ≥ 0.5` (inside TES coverage but missing a value). Outside TES coverage a null need costs no confidence (decision D4). Two or more drops → low. `NO_ATLAS` → low.

## Output (TypeScript)

```ts
type Component = 'native' | 'climate' | 'pest' | 'need';
type Ranked = {
  spcd: number; sciName: string; commonName: string;
  score: number;                                   // 0–100
  components: Record<Component, number | null>;
  diversity: number;                               // 1 or 0.85
  reasons: { code: string; text: string; source: string }[];
  confidence: 'high' | 'medium' | 'low';
  flags: string[];
};
type HexResult = {
  h3: string;
  hexFlags: string[];
  ranked: Ranked[];                                // top 15
  excluded: { spcd: number; gate: 'G1' | 'G2' | 'G3' | 'G4'; reason: string }[];
};
```

## Implementation rules

- One pure function, `rankHex(inputs, weights, scenario): HexResult`, in `app/src/engine/`. No I/O, no globals, no randomness; same inputs give the same output.
- It runs in the Web Worker. The map's best-species metric is the top score per hex in view, recomputed in the worker on weight or scenario change (debounced 100 ms).
- All thresholds live in one constants file that links back to this skill.

## Required tests (Vitest, synthetic fixtures, not real places)

- T1: ash species, emerald ash borer present at severity 10 → no ash ranked; excluded with G2.
- T2: `bps_open_frac 0.8`, `frac_developed 0.1` → `RESTORE_OPEN`.
- T3: forest BpS, canopy 0.70 in 1985 → 0.40 now → `REFOREST`.
- T4: species `no_change` under RCP 4.5 and `decrease` under 8.5 → its rank drops when the scenario switches.
- T5: hex coldest zone 5a, species minimum 6a → G1.
- T6: weights `{native: 1, others: 0}` → order follows the native component, then the tie rules.
- T7: need null inside TES coverage → need skipped, weights renormalized, confidence dropped when the need weight > 0. Need null outside TES coverage → skipped, confidence unchanged.
- T8: Atlas reliability low → confidence at most medium.
- T9: calling twice with the same inputs gives deep-equal results.
- T10: `bps_savanna_frac 0.6`, `frac_developed 0.1` → `RESTORE_SAVANNA`, not `RESTORE_OPEN`; the ranked list is not collapsed.

Phase 1 adds five real hexes from the pilot state, each checked by hand against the source maps: record the hex id, the expected exclusions or top three, and why.
