import { expect, test } from '@playwright/test'
import { PNG } from 'pngjs'
import { deltaE100, openStage, toHex, view } from './helpers'

// viz-style-guide → True data colors: column tops render the exact ramp color. Grain and the
// vignette are CSS overlays over both layers, not part of the data rendering, so they're off here.
test.use({ reducedMotion: 'reduce' })

test('rendered column-top colors match the ramp within ΔE 3', async ({ page }) => {
  await openStage(page, '&grain=0&vignette=0')
  await view(page, { center: [-89.9, 44.75], zoom: 6.6, pitch: 0, bearing: 0 })
  const samples = await page.evaluate(() =>
    window.__stage.topSamples(120).filter((s) => document.elementFromPoint(s.x, s.y)?.classList.contains('maplibregl-canvas')),
  )
  expect(samples.length).toBeGreaterThan(40)

  const png = PNG.sync.read(await page.screenshot())
  const results = samples.map((s) => {
    const x = Math.round(s.x)
    const y = Math.round(s.y)
    const i = (y * png.width + x) * 4
    const got = toHex(png.data[i], png.data[i + 1], png.data[i + 2])
    return { id: s.id, x, y, expected: s.expected, got, dE: deltaE100(got, s.expected) }
  })
  const worst = results.reduce((a, b) => (b.dE > a.dE ? b : a))
  console.log(`sampled ${results.length} tops; worst ΔE×100 = ${worst.dE.toFixed(2)} (${worst.id} at ${worst.x},${worst.y}: ${worst.got} vs ${worst.expected})`)
  expect(worst.dE).toBeLessThanOrEqual(3)
})
