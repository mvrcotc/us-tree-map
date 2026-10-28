#!/usr/bin/env node
/**
 * Bundle budget check (perf-budget → L1, L2). Run after `vite build` (build.manifest: true).
 * Gzips (level 9) every emitted JS file. Lazy = chunks reachable only through dynamic imports
 * from the entry; critical = every other JS file, including the MapLibre and data workers,
 * which load right away. kB = 1,000 bytes, matching Vite's report.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const BUDGET_KB = { L1: 1100, L2: 1300 }

const dist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const manifest = JSON.parse(readFileSync(path.join(dist, '.vite', 'manifest.json'), 'utf8'))

const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const p = path.join(dir, name)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
const jsFiles = walk(dist)
  .filter((p) => /\.m?js$/.test(p))
  .map((p) => path.relative(dist, p).split(path.sep).join('/'))

const entryKey = Object.keys(manifest).find((k) => manifest[k].isEntry)
const closure = (keys, follow) => {
  const seen = new Set()
  const stack = [...keys]
  while (stack.length) {
    const k = stack.pop()
    if (seen.has(k) || !manifest[k]) continue
    seen.add(k)
    stack.push(...(manifest[k].imports ?? []))
    if (follow === 'all') stack.push(...(manifest[k].dynamicImports ?? []))
  }
  return seen
}
const staticKeys = closure([entryKey], 'static')
const allKeys = closure([entryKey], 'all')
const lazyFiles = new Set([...allKeys].filter((k) => !staticKeys.has(k)).map((k) => manifest[k].file))

const gz = (rel) => gzipSync(readFileSync(path.join(dist, rel)), { level: 9 }).length / 1000
const rows = jsFiles.map((file) => ({ file, kB: gz(file), lazy: lazyFiles.has(file) })).sort((a, b) => b.kB - a.kB)

const critical = rows.filter((r) => !r.lazy).reduce((s, r) => s + r.kB, 0)
const all = rows.reduce((s, r) => s + r.kB, 0)

for (const r of rows) console.log(`${r.lazy ? 'lazy    ' : 'critical'}  ${r.kB.toFixed(1).padStart(8)} kB  ${r.file}`)
console.log('')
console.log(`L1 critical-path JS (gzip -9): ${critical.toFixed(1)} kB  (budget ${BUDGET_KB.L1} kB)`)
console.log(`L2 all JS without user action: ${all.toFixed(1)} kB  (budget ${BUDGET_KB.L2} kB)`)

const failed = critical > BUDGET_KB.L1 || all > BUDGET_KB.L2
if (failed) {
  console.error('Bundle budget exceeded (perf-budget).')
  process.exit(1)
}
