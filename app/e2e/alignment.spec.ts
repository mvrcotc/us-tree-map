import { expect, test } from '@playwright/test'
import { openStage, view } from './helpers'

// perf-budget → Rendering rules: the three.js layer matches map.project within 1 px at four angles.
test.use({ reducedMotion: 'reduce' })

const VIEWS = [
  { name: 'top-down', center: [-89.9, 44.8], zoom: 6.4, pitch: 0, bearing: 0 },
  { name: '55° tilt', center: [-89.6, 44.5], zoom: 6.8, pitch: 55, bearing: -20 },
  { name: '70° tilt', center: [-89.4, 44.2], zoom: 7.2, pitch: 70, bearing: 30 },
  { name: 'street zoom', center: [-89.384, 43.074], zoom: 15.5, pitch: 45, bearing: 10 },
] as const

test('three.js layer aligns with map.project at four camera angles', async ({ page }) => {
  test.setTimeout(600_000) // four views, each waiting for street-map tiles on software WebGL
  await openStage(page)
  const report: string[] = []
  for (const v of VIEWS) {
    await view(page, { center: [...v.center], zoom: v.zoom, pitch: v.pitch, bearing: v.bearing })
    // A 5 × 4 grid over the lower 80% of the screen (the top of a tilted view can be sky).
    const errors = await page.evaluate(() => {
      const out: number[] = []
      for (let i = 1; i <= 5; i++)
        for (let j = 2; j <= 5; j++) {
          const { three, map } = window.__stage.compareScreen((innerWidth * i) / 6, (innerHeight * j) / 6)
          out.push(three ? Math.hypot(three[0] - map[0], three[1] - map[1]) : Infinity)
        }
      return out
    })
    const max = Math.max(...errors)
    report.push(`${v.name}: max ${max.toFixed(3)} px over ${errors.length} points`)
    expect(max, v.name).toBeLessThanOrEqual(1)
  }
  console.log(report.join('\n'))
})
