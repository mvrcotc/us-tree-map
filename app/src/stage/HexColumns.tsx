/**
 * Hex columns: one InstancedMesh for the resolution, one draw call, instances in `h3` order
 * (perf-budget → Rendering rules). Year changes copy the current interpolated values into
 * `from`, write the new `to` and restart `uT`, so an interrupted morph never jumps.
 */
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'
import { MAX_COLUMN_M, YEAR_MIN } from '../config'
import type { HexData } from '../data/types'
import { useStore } from '../store'
import { colorOf } from '../theme/ramps'
import { bridge, type ColumnsHandle } from './bridge'
import {
  createColumnMaterial,
  createDepthMaterial,
  RISE_MS,
  RISE_STAGGER_MS,
  SELECTED_LIFT,
  type HexUniforms,
} from './hexMaterial'

/** Year-step morph (viz-style-guide → Motion). */
export const MORPH_MS = 600
/** Columns are drawn at about 94% size so hairline gaps separate them. */
const GAP_SCALE = 0.94

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)
const clamp01 = (t: number) => Math.min(1, Math.max(0, t))

function unitPrism(): THREE.BufferGeometry {
  // Six-sided prism, base at y = 0, height 1; the first vertex points along +z.
  return new THREE.CylinderGeometry(1, 1, 1, 6, 1, false).translate(0, 0.5, 0)
}

class Columns implements ColumnsHandle {
  readonly mesh: THREE.InstancedMesh
  readonly ids: string[]
  private readonly from: THREE.InstancedBufferAttribute
  private readonly to: THREE.InstancedBufferAttribute
  private readonly colorFrom: THREE.InstancedBufferAttribute
  private readonly colorTo: THREE.InstancedBufferAttribute
  private readonly delay: Float32Array
  private readonly pickMesh: THREE.InstancedMesh
  private readonly raycaster = new THREE.Raycaster()
  private morphStart = -Infinity
  private riseStart: number | null = null
  private yearIndex = 0
  private readonly color = new THREE.Color()
  private readonly data: HexData
  private readonly uniforms: HexUniforms
  private readonly reducedMotion: () => boolean

  constructor(data: HexData, uniforms: HexUniforms, reducedMotion: () => boolean) {
    this.data = data
    this.uniforms = uniforms
    this.reducedMotion = reducedMotion
    const n = data.count
    this.ids = data.ids
    const geometry = unitPrism()
    this.from = new THREE.InstancedBufferAttribute(new Float32Array(n), 1)
    this.to = new THREE.InstancedBufferAttribute(new Float32Array(n), 1)
    this.colorFrom = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3)
    this.colorTo = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3)
    this.delay = new Float32Array(n)
    let minX = Infinity
    let maxX = -Infinity
    for (let i = 0; i < n; i++) {
      minX = Math.min(minX, data.x[i])
      maxX = Math.max(maxX, data.x[i])
    }
    for (let i = 0; i < n; i++) this.delay[i] = ((data.x[i] - minX) / (maxX - minX || 1)) * RISE_STAGGER_MS
    geometry.setAttribute('aFrom', this.from)
    geometry.setAttribute('aTo', this.to)
    geometry.setAttribute('aColorFrom', this.colorFrom)
    geometry.setAttribute('aColorTo', this.colorTo)
    geometry.setAttribute('aDelay', new THREE.InstancedBufferAttribute(this.delay, 1))
    geometry.setAttribute('aHex', new THREE.InstancedBufferAttribute(new Float32Array(n).fill(1), 1))

    this.mesh = new THREE.InstancedMesh(geometry, createColumnMaterial(this.uniforms), n)
    this.mesh.customDepthMaterial = createDepthMaterial(this.uniforms)
    this.mesh.castShadow = true
    this.mesh.receiveShadow = true
    this.mesh.frustumCulled = false

    const m = new THREE.Matrix4()
    const q = new THREE.Quaternion()
    const up = new THREE.Vector3(0, 1, 0)
    for (let i = 0; i < n; i++) {
      q.setFromAxisAngle(up, data.rotation[i])
      const r = data.radius[i] * GAP_SCALE
      m.compose(new THREE.Vector3(data.x[i], 0, data.z[i]), q, new THREE.Vector3(r, 1, r))
      this.mesh.setMatrixAt(i, m)
    }
    this.mesh.instanceMatrix.needsUpdate = true

    // Picking copy (never drawn): same prisms with heights baked in at pick time.
    this.pickMesh = new THREE.InstancedMesh(unitPrism(), new THREE.MeshBasicMaterial(), n)
  }

  /** Current interpolated height of an instance, matching the vertex shader. */
  heightAt(i: number): number {
    const e = easeInOut(clamp01(this.uniforms.uT.value))
    const rise = easeOut(clamp01((this.uniforms.uRise.value - this.delay[i]) / RISE_MS))
    const lift = i === this.uniforms.uSelected.value ? 1 + SELECTED_LIFT : 1
    return Math.max(1, (this.from.array[i] + (this.to.array[i] - this.from.array[i]) * e) * rise * lift)
  }

  setYear(year: number, animate: boolean) {
    const ny = this.data.years.length
    const j = Math.min(ny - 1, Math.max(0, year - YEAR_MIN))
    this.yearIndex = j
    const e = easeInOut(clamp01(this.uniforms.uT.value))
    const from = this.from.array as Float32Array
    const to = this.to.array as Float32Array
    const cFrom = this.colorFrom.array as Float32Array
    const cTo = this.colorTo.array as Float32Array
    for (let i = 0; i < this.data.count; i++) {
      from[i] = from[i] + (to[i] - from[i]) * e
      for (let c = 0; c < 3; c++) cFrom[i * 3 + c] = cFrom[i * 3 + c] + (cTo[i * 3 + c] - cFrom[i * 3 + c]) * e
      const v = this.data.values[i * ny + j]
      to[i] = v * MAX_COLUMN_M
      // THREE.Color parses sRGB hex into the linear working space; the shader outputs it back exactly.
      this.color.set(colorOf(v))
      cTo[i * 3] = this.color.r
      cTo[i * 3 + 1] = this.color.g
      cTo[i * 3 + 2] = this.color.b
    }
    this.from.needsUpdate = this.to.needsUpdate = this.colorFrom.needsUpdate = this.colorTo.needsUpdate = true
    if (animate) {
      this.uniforms.uT.value = 0
      this.morphStart = performance.now()
    } else {
      this.uniforms.uT.value = 1
      this.morphStart = -Infinity
    }
  }

  select(index: number) {
    this.uniforms.uSelected.value = index
  }

  tick(now: number): boolean {
    if (this.reducedMotion()) {
      this.uniforms.uRise.value = 1e9
      this.uniforms.uT.value = 1
      return false
    }
    if (this.riseStart === null) this.riseStart = now
    this.uniforms.uRise.value = now - this.riseStart
    if (this.morphStart > -Infinity) this.uniforms.uT.value = clamp01((now - this.morphStart) / MORPH_MS)
    return !this.idle()
  }

  idle(): boolean {
    return this.uniforms.uT.value >= 1 && this.uniforms.uRise.value >= RISE_MS + RISE_STAGGER_MS
  }

  pick(px: number, py: number): number {
    const camera = bridge.camera
    const map = bridge.map
    if (!camera || !map) return -1
    const m = new THREE.Matrix4()
    const pos = new THREE.Vector3()
    const q = new THREE.Quaternion()
    const scale = new THREE.Vector3()
    for (let i = 0; i < this.data.count; i++) {
      this.mesh.getMatrixAt(i, m)
      m.decompose(pos, q, scale)
      scale.y = this.heightAt(i)
      this.pickMesh.setMatrixAt(i, m.compose(pos, q, scale))
    }
    this.pickMesh.instanceMatrix.needsUpdate = true
    this.pickMesh.computeBoundingSphere()
    const canvas = map.getCanvas()
    const ndc = new THREE.Vector2((px / canvas.clientWidth) * 2 - 1, -(py / canvas.clientHeight) * 2 + 1)
    this.raycaster.setFromCamera(ndc, camera)
    const hit = this.raycaster.intersectObject(this.pickMesh, false)[0]
    return hit?.instanceId ?? -1
  }

  topCenter(i: number): THREE.Vector3 {
    return new THREE.Vector3(this.data.x[i], this.heightAt(i), this.data.z[i])
  }

  /** Free GPU buffers and programs (a resolution switch re-creates the columns). */
  dispose() {
    this.mesh.geometry.dispose()
    ;(this.mesh.material as THREE.Material).dispose()
    this.mesh.customDepthMaterial?.dispose()
    this.mesh.dispose()
    this.pickMesh.geometry.dispose()
    ;(this.pickMesh.material as THREE.Material).dispose()
    this.pickMesh.dispose()
  }

  lngLat(i: number): [number, number] {
    return [this.data.lng[i], this.data.lat[i]]
  }

  expectedColor(i: number): string {
    const ny = this.data.years.length
    return colorOf(this.data.values[i * ny + this.yearIndex])
  }
}

export function HexColumns({ data, uniforms }: { data: HexData; uniforms: HexUniforms }) {
  const columns = useMemo(() => new Columns(data, uniforms, () => useStore.getState().reducedMotion), [data, uniforms])

  useEffect(() => {
    columns.setYear(useStore.getState().year, false)
    bridge.columns = columns
    bridge.map?.triggerRepaint()
    const unsubscribe = useStore.subscribe((state, prev) => {
      if (state.year !== prev.year) columns.setYear(state.year, !state.reducedMotion)
      if (state.selectedH3 !== prev.selectedH3) columns.select(state.selectedH3 ? columns.ids.indexOf(state.selectedH3) : -1)
      bridge.map?.triggerRepaint()
    })
    return () => {
      unsubscribe()
      if (bridge.columns === columns) bridge.columns = null
      columns.dispose()
    }
  }, [columns])

  return <primitive object={columns.mesh} />
}
