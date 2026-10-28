import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { createReadStream, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Connect, Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

const here = path.dirname(fileURLToPath(import.meta.url))
const DATA_OUT = path.resolve(here, '..', 'data', 'out')

const TYPES: Record<string, string> = {
  '.json': 'application/json',
  '.parquet': 'application/vnd.apache.parquet',
}

/**
 * Serves the pipeline's local output (data/out/) at /data/ in dev and preview, standing in for
 * R2 until Phase 5. Production builds read VITE_DATA_BASE instead.
 */
function localData(): Plugin {
  const handler: Connect.NextHandleFunction = (req, res, next) => {
    const rel = decodeURIComponent((req.url ?? '/').split('?')[0])
    const file = path.resolve(DATA_OUT, '.' + rel)
    if (!file.startsWith(DATA_OUT + path.sep)) return next()
    try {
      const stat = statSync(file)
      if (!stat.isFile()) return next()
      res.setHeader('Content-Type', TYPES[path.extname(file)] ?? 'application/octet-stream')
      res.setHeader('Content-Length', String(stat.size))
      createReadStream(file).pipe(res)
    } catch {
      next()
    }
  }
  return {
    name: 'local-data',
    configureServer: (server) => void server.middlewares.use('/data', handler),
    configurePreviewServer: (server) => void server.middlewares.use('/data', handler),
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), localData()],
  build: { manifest: true, target: 'es2023' },
  worker: { format: 'es' },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
