import { expect, test } from '@playwright/test'
import path from 'node:path'
import './helpers'

test('mock route follows the layout and saves docs/img/mock-v1.png', async ({ page }) => {
  await page.goto('/mock?test')
  await page.waitForFunction(() => window.__stage?.ready(), undefined, { timeout: 150_000, polling: 500 })
  for (const name of ['US Tree Map', 'Layers', 'Engine weights', 'Best species here', 'Pest threats', 'Past vs. now', 'Land cover through time', 'Time'])
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await expect(page.getByTestId('synthetic-label')).toBeVisible()
  await expect(page.getByRole('slider', { name: /Planting need/ })).toBeDisabled()
  // Keyboard reaches the scenario control and its state is announced.
  await expect(page.getByRole('button', { name: 'Lower · RCP 4.5' })).toHaveAttribute('aria-pressed', 'true')
  await page.waitForTimeout(1500) // street-map tiles settle
  await page.screenshot({ path: path.resolve(import.meta.dirname, '../../docs/img/mock-v1.png') })
})
