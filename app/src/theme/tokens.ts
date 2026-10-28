/**
 * Design tokens from viz-style-guide (UI chrome, Stage, chart rules, motion). The CSS
 * custom properties in tokens.css mirror the chrome values for Tailwind; keep them in sync
 * (tokens.test.ts checks the contrast rules on these values).
 *
 * Direction (Marco): clean, minimal, soft and rounded, editorial; muted blues; nothing rigid.
 */

/** UI chrome. The accent marks interactive state only and never appears on the map or in a chart. */
export const chrome = {
  page: '#f4f6f8',
  surface: '#ffffff',
  surfaceMuted: '#eef2f5',
  hairline: '#e2e7ec',
  accent: '#4a6f94',
  accentSoft: '#dfe8f1',
  focusRing: '#4a6f94',
} as const

/**
 * Text inks on light surfaces (viz-style-guide → Chart rules). Muted ink is ~3.5:1, so it is for
 * non-text marks and text ≥ 18 px only; smaller text uses secondary ink (WCAG AA 4.5:1).
 */
export const ink = {
  primary: '#0b0b0b',
  secondary: '#52514e',
  muted: '#898781',
} as const

export const radius = { panel: 16, control: 12, pill: 999 } as const

export const shadow = {
  soft: '0 1px 2px rgb(20 30 45 / 0.06), 0 8px 24px rgb(20 30 45 / 0.08)',
} as const

export const font = {
  serif: "'Iowan Old Style', 'Charter', 'Palatino Linotype', Georgia, serif",
  sans: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
} as const

/** Land cover and past-vs-now categories, in stack order bottom → top (viz-style-guide). */
export const landCover = {
  light: { forest: '#008300', grass: '#eda100', crop: '#6250d6', developed: '#e34948', other: '#898781' },
  dark: { forest: '#008300', grass: '#c98500', crop: '#9085e9', developed: '#e66767', other: '#898781' },
} as const
export const LAND_COVER_ORDER = ['forest', 'grass', 'crop', 'developed', 'other'] as const

/** Species score segments, fixed order native, climate, pest, need. */
export const scoreComponents = { native: '#2a78d6', climate: '#eb6834', pest: '#1baf7a', need: '#eda100' } as const

/** No data: not extruded, hairline outline only; never the low end of a ramp. */
export const noData = { fill: 'transparent', outline: '#9aa3ad' } as const

/** Motion timings in ms (viz-style-guide → Motion). Reduced motion sets every duration to 0. */
export const motion = {
  yearStep: 600,
  metricChange: 800,
  introTotal: 1200,
  introPerColumn: 600,
  chartUpdate: 500,
  flyTo: 1500,
  cityHandoff: 600,
  panelEnter: 200,
  panelExit: 150,
  playStep: 900,
} as const

/** Stage art direction (viz-style-guide → Stage). */
export const stage = {
  keyLight: { color: '#fff1dc', fromDirection: 'northwest' },
  skyFill: { sky: '#e3edf7', ground: '#b8ab95' },
  shadowOpacity: 0.16,
  vignetteMaxDarkness: 0.35,
  grainMaxOpacity: 0.03,
} as const
