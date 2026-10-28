/** viz-style-guide → How to check a palette change. */
import { schemeBlues, schemeBrBG, schemeGreens, schemeOranges, schemePuOr } from 'd3-scale-chromatic'
import { describe, expect, it } from 'vitest'
import { contrast, deltaE, deltaECvd, oklch } from './colorMath'
import { GREENS_6 } from './ramps'
import { chrome, ink, LAND_COVER_ORDER, landCover, scoreComponents } from './tokens'

const sequential = {
  'pest pressure (Oranges 2–7)': schemeOranges[7].slice(1),
  'planting need (Blues 2–7)': schemeBlues[7].slice(1),
  'best-species score (Greens 2–7)': schemeGreens[7].slice(1),
}
// Diverging arms without the neutral midpoint, light → dark. The midpoint differs from the first
// colored step by hue and chroma; its lightness gap is smaller (0.037–0.060, see viz-style-guide).
// d3's schemePuOr runs purple → orange; the guide reverses it so decrease is orange.
const divergingArms = {
  'canopy loss (BrBG)': schemeBrBG[7].slice(0, 3).reverse(),
  'canopy gain (BrBG)': schemeBrBG[7].slice(4),
  'habitat increase (PuOr, purple)': schemePuOr[7].slice(0, 3).reverse(),
  'habitat decrease (PuOr, orange)': schemePuOr[7].slice(4),
}

const hueSpread = (hexes: readonly string[]) => {
  const hues = hexes.map(oklch).filter((c) => c.c > 0.02).map((c) => c.h)
  return hues.length < 2 ? 0 : Math.max(...hues) - Math.min(...hues)
}

describe('map metric ramps', () => {
  it('the stage uses schemeGreens[7] steps 2–7 for best-species score', () => {
    expect(GREENS_6).toEqual(['#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#005a32'])
  })

  for (const [name, ramp] of Object.entries({ ...sequential, ...divergingArms })) {
    it(`${name}: lightness strictly falls by ≥ 0.06 per step, one hue family`, () => {
      const l = ramp.map((c) => oklch(c).l)
      for (let i = 1; i < l.length; i++) expect(l[i - 1] - l[i]).toBeGreaterThanOrEqual(0.06)
      expect(hueSpread(ramp)).toBeLessThan(60)
    })
  }
})

describe('categorical sets', () => {
  const sets = {
    'land cover (light)': LAND_COVER_ORDER.map((k) => landCover.light[k]),
    'species score segments': Object.values(scoreComponents),
  }
  for (const [name, colors] of Object.entries(sets)) {
    it(`${name}: adjacent pairs ≥ 15 normal vision and ≥ 6 under protanopia/deuteranopia`, () => {
      for (let i = 1; i < colors.length; i++) {
        expect(deltaE(colors[i - 1], colors[i])).toBeGreaterThanOrEqual(15)
        // 6–8 is allowed only with direct labels or 2 px gaps, which these charts require.
        for (const kind of ['protanopia', 'deuteranopia'] as const) expect(deltaECvd(colors[i - 1], colors[i], kind)).toBeGreaterThanOrEqual(6)
      }
    })
  }
})

describe('chrome contrast', () => {
  it('focus ring and accent ≥ 3:1 on page and surface', () => {
    for (const bg of [chrome.page, chrome.surface, chrome.surfaceMuted]) expect(contrast(chrome.focusRing, bg)).toBeGreaterThanOrEqual(3)
  })
  it('primary and secondary ink ≥ 4.5:1 on every surface; muted ink ≥ 3:1', () => {
    for (const bg of [chrome.page, chrome.surface, chrome.surfaceMuted]) {
      expect(contrast(ink.primary, bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(ink.secondary, bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(ink.muted, bg)).toBeGreaterThanOrEqual(3)
    }
  })
})
