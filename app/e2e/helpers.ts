import type { Page } from '@playwright/test'
import type { StageTestApi } from '../src/stage/testHooks'

declare global {
  interface Window {
    __stage: StageTestApi
  }
}

export async function openStage(page: Page, query = '') {
  await page.goto(`/?test${query}`)
  await page.waitForFunction(() => window.__stage?.ready(), undefined, { timeout: 150_000, polling: 500 })
}

export async function view(page: Page, options: { center: [number, number]; zoom: number; pitch: number; bearing?: number }) {
  await page.evaluate((o) => window.__stage.jumpTo(o), options)
  await page.waitForFunction(() => window.__stage.ready(), undefined, { polling: 250 })
}

/** sRGB hex → OKLab (Björn Ottosson). */
export function oklab(hex: string): [number, number, number] {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  const [r, g, b] = c
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

/** OKLab ΔE × 100 (viz-style-guide → True data colors). */
export function deltaE100(a: string, b: string): number {
  const [x, y] = [oklab(a), oklab(b)]
  return 100 * Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2])
}

export const toHex = (r: number, g: number, b: number) => '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')
