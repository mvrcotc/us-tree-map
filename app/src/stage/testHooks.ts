/**
 * Test-only hooks, installed with `?test`: lets Playwright check layer alignment against
 * `map.project` and sample column-top colors (perf-budget → Rendering rules; viz-style-guide).
 */
import * as THREE from 'three'
import { bridge } from './bridge'
import { localFrame } from '../geo/mercator'
import { ORIGIN_LNGLAT } from '../config'
import { useStore } from '../store'

const frame = localFrame(ORIGIN_LNGLAT)

/** Screen position (CSS px) of a local-frame point through the synced three.js camera. */
function projectLocal(p: THREE.Vector3): [number, number] | null {
  const camera = bridge.camera
  const canvas = bridge.map?.getCanvas()
  if (!camera || !canvas) return null
  const v = p.clone().project(camera)
  return [((v.x + 1) / 2) * canvas.clientWidth, ((1 - v.y) / 2) * canvas.clientHeight]
}

export type StageTestApi = {
  ready(): boolean
  /** [three.js px, map.project px] for a ground point. */
  compare(lng: number, lat: number): { three: [number, number] | null; map: [number, number] }
  /** Same, for the ground point under a screen position. */
  compareScreen(x: number, y: number): { three: [number, number] | null; map: [number, number] }
  /** Top-center screen positions and expected sRGB colors of up to `n` evenly spaced columns. */
  topSamples(n: number): { id: string; x: number; y: number; expected: string }[]
  jumpTo(options: { center: [number, number]; zoom: number; pitch: number; bearing?: number }): Promise<void>
  selected(): string | null
  zoom(): number
}

export function installTestHooks() {
  const api: StageTestApi = {
    // Ready once a synced frame with columns has drawn and nothing is animating.
    ready: () => Boolean(useStore.getState().firstHexFrame && bridge.map?.loaded() && bridge.columns?.idle()),
    compare(lng, lat) {
      const [x, z] = frame.toLocal(lng, lat)
      const p = bridge.map!.project([lng, lat])
      return { three: projectLocal(new THREE.Vector3(x, 0, z)), map: [p.x, p.y] }
    },
    compareScreen(x, y) {
      const { lng, lat } = bridge.map!.unproject([x, y])
      return api.compare(lng, lat)
    },
    topSamples(n) {
      const c = bridge.columns
      if (!c) return []
      const step = Math.max(1, Math.floor(c.ids.length / n))
      const out = []
      for (let i = 0; i < c.ids.length && out.length < n; i += step) {
        const s = projectLocal(c.topCenter(i))
        if (s && Number.isFinite(s[0]) && Number.isFinite(s[1])) out.push({ id: c.ids[i], x: s[0], y: s[1], expected: c.expectedColor(i) })
      }
      return out
    },
    selected: () => useStore.getState().selectedH3,
    zoom: () => bridge.map!.getZoom(),
    jumpTo(options) {
      const map = bridge.map!
      return new Promise((resolve) => {
        map.once('idle', () => resolve())
        map.jumpTo(options)
        map.triggerRepaint()
      })
    },
  }
  ;(window as unknown as { __stage: StageTestApi }).__stage = api
}
