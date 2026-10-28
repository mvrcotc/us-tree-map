/**
 * Synthetic smoke-test values (Phase 0). Deterministic, smooth in space and time, and always
 * labeled "synthetic data" in the UI. Never shown as real data (CLAUDE.md hard rule 1).
 */
import { YEAR_MAX, YEAR_MIN } from '../config'

function hash01(id: string): number {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619)
  return ((h >>> 0) % 10_000) / 10_000
}

export function syntheticValue(id: string, lng: number, lat: number, year: number): number {
  const t = (year - YEAR_MIN) / (YEAR_MAX - YEAR_MIN)
  const base = 0.5 + 0.28 * Math.sin(lat * 1.9 + lng * 0.8) + 0.14 * Math.cos(lng * 2.6 - lat * 0.7)
  const trend = 0.3 * t * Math.sin(lng * 1.4 + lat * 1.1)
  const v = base + trend + 0.08 * (hash01(id) - 0.5)
  return Math.min(1, Math.max(0, v))
}
