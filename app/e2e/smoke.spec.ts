import { expect, test } from '@playwright/test'
import path from 'node:path'
import { openStage } from './helpers'

test('smoke: map, synced 3D columns, synthetic label, chart; saves docs/img/smoke.png', async ({ page }) => {
  await openStage(page)
  await expect(page.getByTestId('synthetic-label')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'State mean score by year' })).toBeVisible()
  await expect(page.getByRole('slider')).toHaveValue('2024')
  await page.waitForTimeout(1500) // let street-map tiles settle
  await page.screenshot({ path: path.resolve(import.meta.dirname, '../../docs/img/smoke.png') })
})

test('year slider drives the store and the chart marker', async ({ page }) => {
  await openStage(page)
  const slider = page.getByRole('slider')
  await slider.focus()
  await page.keyboard.press('Home')
  await expect(slider).toHaveValue('1985')
  await expect(page.locator('output')).toHaveText('1985')
  await page.waitForFunction(() => window.__stage.ready())
})

test.describe('reduced motion', () => {
  test.use({ reducedMotion: 'reduce' })

  test('click a hex: it is selected and the camera jumps to it', async ({ page }) => {
    await openStage(page)
    // A column top that isn't under a UI panel (the three.js canvas ignores pointer events).
    const sample = await page.evaluate(() =>
      window.__stage.topSamples(400).filter((s) => document.elementFromPoint(s.x, s.y)?.classList.contains('maplibregl-canvas'))[200],
    )
    await page.mouse.click(sample.x, sample.y)
    await expect.poll(() => page.evaluate(() => window.__stage.selected())).toBe(sample.id)
    await expect.poll(() => page.evaluate(() => window.__stage.zoom())).toBeCloseTo(9.5, 1)
  })
})
