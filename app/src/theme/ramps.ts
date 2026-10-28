/**
 * Map metric ramps (viz-style-guide → Map metric ramps). Colors come from d3-scale-chromatic
 * (ColorBrewer), never retyped. Breaks are fixed per metric, not per view.
 */
import { schemeGreens } from 'd3-scale-chromatic'

/** Best-species score: schemeGreens[7] steps 2–7, six classes over 0–1. */
export const GREENS_6: readonly string[] = schemeGreens[7].slice(1)

/** Upper bounds of each class (exclusive) for a 0–1 value; the last class takes the rest. */
export const BREAKS_6 = [1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6] as const

export function classOf(value: number): number {
  let i = 0
  while (i < BREAKS_6.length && value >= BREAKS_6[i]) i++
  return i
}

export const colorOf = (value: number) => GREENS_6[classOf(value)]
