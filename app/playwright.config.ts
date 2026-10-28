import { defineConfig, devices } from '@playwright/test'

/**
 * E2E against the production build served by `vite preview` (which also serves data/out/ at /data/).
 * Headless Chromium may fall back to software WebGL: slow, but exact for alignment and colors.
 * Never use these runs for frame times (perf-budget → Reference setup).
 */
export default defineConfig({
  testDir: 'e2e',
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:4173',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    ...devices['Desktop Chrome'],
  },
  projects: [{ name: 'chromium', use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 } }],
  webServer: {
    command: 'npm run build && npx vite preview --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
