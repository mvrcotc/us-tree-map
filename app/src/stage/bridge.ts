/**
 * Plain mutable references shared by MapLibre's custom layer and the three.js scene.
 * Per-frame work reads these, never React state (perf-budget → Rendering rules).
 */
import type { Map as MLMap } from 'maplibre-gl'
import type * as THREE from 'three'

export type ColumnsHandle = {
  /** Advance uniforms to `now`; returns true while a morph or the intro rise is running. */
  tick(now: number): boolean
  /** Instance index under a pointer (CSS px relative to the map canvas), or -1. */
  pick(px: number, py: number): number
  /** Local-frame top centers of the given instances at their current heights. */
  topCenter(index: number): THREE.Vector3
  ids: string[]
  lngLat(index: number): [number, number]
  /** Expected sRGB hex color of an instance's top at the current year. */
  expectedColor(index: number): string
  idle(): boolean
}

export const bridge: {
  map: MLMap | null
  camera: THREE.PerspectiveCamera | null
  columns: ColumnsHandle | null
} = { map: null, camera: null, columns: null }
