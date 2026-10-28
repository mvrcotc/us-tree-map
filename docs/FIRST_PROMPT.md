# Start here: Phase 0 in Claude Code

## Open the project

In the Claude desktop app:

1. Open the **Code** tab.
2. In the row under the prompt box, set the environment to **Local** and the project folder to `/Volumes/Backup One/Business/Code Projects/US Tree Map` (the drive must be connected). Use Local, not Cloud: Phase 1 downloads large federal rasters and processes them on your disk.
3. Set the mode to **Plan** for the first message.
4. Leave the model on the default, Opus 5.5.
5. Paste the prompt below.

The Claude Code config (four skills, the reviewer agent, `settings.json`) is in `claude-setup/` for now, because Claude's remote file tools aren't allowed to write into `.claude/`. Step 0 of the prompt moves it into place.

In a terminal instead: `cd "/Volumes/Backup One/Business/Code Projects/US Tree Map"`, run `claude`, and start in plan mode.

## The prompt

```text
This is the US Tree Map. Read CLAUDE.md, docs/PLAN.md (Corrections first) and the four project skills (in claude-setup/skills/ until step 0 moves them to .claude/skills/). We're doing Phase 0. Plan it, show me the plan, and wait for my OK before changing anything.

Phase 0, in this order. Commit after each step from step 1 on.

0. Setup. Copy everything inside claude-setup/ into .claude/ with cp -R claude-setup/. .claude/ (it merges into the empty folders already there). Check that .claude/ now has settings.json, agents/reviewer.md and four skills/*/SKILL.md, then delete claude-setup/.

1. Repo. git init and commit the kit as-is. Ask me: public or private GitHub repo (the plan assumes public, which keeps GitHub Actions free), and which code license (suggest MIT; data outputs keep each source's terms). Create the repo with gh if it's installed and logged in; otherwise give me the exact steps.

2. Pilot state. Propose three eastern states inside Tree Atlas coverage, at least one with a large prairie or savanna history so the restoration flag gets exercised. Compare: area and hex counts at res 5-7, notable forest pests present, cities covered by Tree Equity Score, historical forest vs. open share (LANDFIRE BpS), and forest loss since 1985. Open the sources; mark anything you can't confirm "unverified". Recommend one; I choose.

3. Decisions. Walk me through D1-D8 in the data contract one at a time: the options, your recommendation and why, in five lines or fewer. Wait for my answer, write it into the skill, and remove it from the open list.

4. Sources. Fill the Verified column for every source still marked "—": access method, current version, license or terms, and download size. Draft the email asking American Forests for permission to publish hex values derived from Tree Equity Score (D7).

5. Numbers. Put every v0 number from species-engine-rules and perf-budget in one table so I can confirm or change them in one pass.

6. Pipeline scaffold in pipeline/: Python 3.13 with uv; duckdb, h3, rasterio, pyproj, pyarrow, numpy, pytest. First step: from the Census state boundary, build hex_base's h3, res and p3 columns for the pilot state at res 5-8 (other columns NULL until their sources land) and the state outline under geo/, both per the data contract, with a pytest for roll-up consistency.

7. App scaffold in app/: npm create vite@latest app -- --template react-ts. Keep its TypeScript 7 and oxlint. Add, with exact versions pinned: maplibre-gl 6; three 0.186.x; @react-three/fiber 9; @react-three/drei 10; @react-three/postprocessing 3 with postprocessing 6; h3-js 4; echarts 6; zustand 5; d3-scale-chromatic; hyparquet; tailwindcss 4 with @tailwindcss/vite; vitest; @playwright/test. Smoke screen, following viz-style-guide's Stage section and the map + 3D layer sync recipe in CLAUDE.md's Gotchas: a MapLibre street map (OpenFreeMap Positron) showing the state outline from step 6; a transparent three.js canvas on top, its camera synced through a MapLibre custom layer; the res-6 hexes from step 6 as one InstancedMesh with synthetic values, labeled "synthetic data"; column shadows on the map; the intro rise; a year slider in the Zustand store driving the 600 ms shader morph; click a hex to fly to it with MapLibre's flyTo; the High-tier effects; and one ECharts panel, loaded after the first frame with hexes, reading the same store. Tests: a Vitest test for the store, and Playwright tests that save docs/img/smoke.png, check rendered column-top colors against the ramp (the true-data-color rule), and check layer alignment against map.project at four camera angles (perf-budget). Add app/scripts/size.mjs per perf-budget and report L1 and L2.

8. Look. Turn viz-style-guide, including its UI chrome and Stage sections, into design tokens in app/src/theme/, plus a muted version of the Positron map style. Build a static /mock route that follows docs/img/layout.png with placeholder panels, and save a Playwright screenshot to docs/img/mock-v1.png for my review.

9. Wrap-up. Update the Status and Commands sections of CLAUDE.md. Run the reviewer subagent and fix what it finds. Phase 0 is done when I approve the mock and the data contract.
```

## Models for Phase 0

- **Steps 0, 1, 6, 7:** Opus 5.5, the default.
- **Steps 2–5 (decisions):** Fable 5.1 (`/model fable`) if your plan includes it. Depending on plan and seat, Fable can bill to usage credits; Claude Code asks before it does. Otherwise stay on Opus 5.5 at `/effort high`.
- **Step 8:** Sonnet 5.5 is enough (`/model sonnet`).

In the desktop app, switch models with the model picker under the prompt box.

## Later phases

One session per phase is plenty. Each phase plans first and ends with the reviewer subagent and the gate evidence (CLAUDE.md already tells Claude this).

| Phase | Paste | Model |
| --- | --- | --- |
| 1 · Data pipeline | Start Phase 1 from docs/PLAN.md and the data contract. Plan first. Before downloading anything, tell me file sizes and the disk space needed. One layer per step, each with tests; finish with the 20-hex spot check. | Opus 5.5 |
| 2 · 3D stage | Start Phase 2 from docs/PLAN.md and viz-style-guide's Stage section, including the city-view handoff to the street map. Plan first. Finish by measuring F1–F5 from perf-budget on my laptop. | Opus 5.5; Fable 5.1 for a rendering or shader bug Opus can't fix |
| 3 · Charts + engine | Start Phase 3. Build the species engine and tests T1–T9 first, then the six linked panels. Finish by measuring U1–U3. | Opus 5.5 for the engine, Sonnet 5.5 for the panels |
| 4 · Polish | Start Phase 4: motion, guided tour, quality tiers, mobile layout, source links, accessibility; the optional procedural trees if time allows. Finish with the accessibility review and L1–L4. | Sonnet 5.5; Opus 5.5 for the tour's camera choreography |
| 5 · Launch | Start Phase 5: deploy to Cloudflare Pages and R2, add the feedback form, run the launch checklist. | Sonnet 5.5 |

The project's state lives in the repo, not the chat: CLAUDE.md's Status section says where things stand, so any new session can pick up from it.
