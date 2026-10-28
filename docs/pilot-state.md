# Pilot state: Wisconsin

Chosen by Marco on Oct 27, 2026, from the comparison below (Phase 0, step 2).

## Comparison

Hex counts: H3 v4 cells whose center is inside the Census 2024 cartographic boundary (`cb_2024_us_state_500k`); cells touching the boundary in parentheses. Area: Census `ALAND` / `AWATER` (Wisconsin's water includes its Great Lakes waters).

| | Wisconsin | Missouri | Pennsylvania |
| --- | --- | --- | --- |
| Land / water area | 140,295 / 29,341 km² | 178,052 / 2,487 km² | 115,881 / 3,398 km² |
| Res 5 | 549 (659) | 704 (783) | 460 (518) |
| Res 6 | 3,845 (4,096) | 4,937 (5,143) | 3,216 (3,370) |
| Res 7 | 26,903 (27,547) | 34,493 (35,094) | 22,512 (22,922) |
| Res 8 (pipeline grid) | 188,282 (190,023) | 241,408 (243,083) | 157,594 (158,679) |
| Notable forest pests | EAB in all 72 counties; oak wilt in 66 counties; spongy moth (outbreak peaked 2023, collapsed 2024); beech bark disease in Door and Menominee counties [1][2] | EAB in 111 of 114 counties; oak decline; no reproducing spongy moth; thousand cankers on black walnut (current status unverified); no spotted lanternfly detected in 2025 surveys [3] | EAB in every county; spongy moth (about 3/4 of 794,000 damaged acres in 2024); hemlock woolly adelgid; beech leaf disease (~34,900 acres in 2024); oak wilt; spotted lanternfly quarantine in 56 counties [4][5] |
| Tree Equity Score cities | Covers Census urban areas (e.g. Milwaukee, Madison, Green Bay); per-state count unverified | St. Louis, Kansas City, Springfield; count unverified | Philadelphia, Pittsburgh, Allentown; count unverified |
| Historical forest vs. open (LANDFIRE BpS) | Not computed yet (Phase 1). Literature: about 9.5 million acres of prairie and oak savanna (~22% of land area) [6]; savanna and prairie about 50% of southern Wisconsin [7] | Not computed yet. Literature: about 1/3 of the state tallgrass prairie including savanna [8] | Not computed yet. Overwhelmingly forest; small serpentine barrens and grasslands (unverified share) |
| Forest change since 1985 | Not computed yet (Annual NLCD, Phase 1). FIA suggests forest area has increased over recent decades [9] | Unverified | Unverified; still >58% tree cover |

Coverage: all three are fully inside Tree Atlas coverage (eastern US). All fit perf-budget M1 (≤ 60,000 instances) even at res 7 for the whole state.

## Why Wisconsin

- A sharp gradient from southern prairie and oak savanna to northern forest exercises `RESTORE_OPEN`, `REFOREST` and decision D8 (savanna) in one state.
- Several major pests at different stages (EAB everywhere, oak wilt spreading, spongy moth after an outbreak, beech bark disease at its front) exercise the pest gate and the pest component.
- Mid-sized data: 3,845 res-6 hexes for the state view.
- Watch out for: Great Lakes shoreline and islands (edge hexes, Tree Atlas pooling near water).

## Sources

1. [Wisconsin DNR, 2024 Forest Health Annual Report](https://forestrynews.blogs.govdelivery.com/2025/01/08/2024-forest-health-annual-report-published/)
2. [Wisconsin DNR, 2025 Forest Health Annual Report](https://forestrynews.blogs.govdelivery.com/?p=12440)
3. [USDA Forest Service, Missouri forest health highlights](https://apps.fs.usda.gov/nicportal/temppdf/sfs/naweb/MO_std.pdf)
4. [USDA Forest Service, Pennsylvania Forest Health Highlights 2024](https://www.fs.usda.gov/foresthealth/docs/fhh/PA_FHH_2024.pdf) and [2025](https://www.fs.usda.gov/foresthealth/docs/fhh/PA_FHH_2025.pdf)
5. [PSATS: counties added to Pennsylvania's spotted lanternfly quarantine](https://www.psats.org/?p=26040) (spring 2025)
6. [USFWS / Recreation.gov, Leopold Wetland Management District](https://www.recreation.gov/gateways/1483) (secondary source)
7. [Will-Wolf and Montague, EPA ecological conference archive](https://archive.epa.gov/ecopage/web/html/will-wolf.html)
8. [Missouri Department of Conservation, Show-Me Prairie and Grassland Conservation](https://mdc.mo.gov/magazines/conservationist/2017-07/show-me-prairie-grassland-conservation)
9. [Wisconsin Council on Forestry 2021–2022 biennial report](https://docs.legis.wisconsin.gov/misc/mandatedreports/2023/department_of_natural_resources/2021_2022_council_on_forestry_biennial_report_s_26_02_2_b_received_6_1_2023.pdf)

Literature figures are context only. The app's values come from the pipeline (hard rule 1).

## Shipped hex counts (pipeline, Oct 27, 2026)

`hex_base` takes the res-8 cells whose centers fall inside the 2025 Census boundary and builds coarser resolutions as their parents, so edge hexes are whole: res 5 = 625, res 6 = 4,037, res 7 = 27,304, res 8 = 188,282.
