/**
 * MapLibre custom layer that drives the three.js layer (CLAUDE.md → Gotchas → Map + 3D layer sync).
 * It draws nothing itself: in `render` it copies MapLibre's camera into the three.js camera,
 * then calls React Three Fiber's `advance()`, so both layers draw in the same frame.
 */
import { advance } from '@react-three/fiber'
import { MercatorCoordinate, type CustomLayerInterface, type CustomRenderMethodInput } from 'maplibre-gl'
import * as THREE from 'three'
import { ORIGIN_LNGLAT } from '../config'
import { useStore } from '../store'
import { bridge } from './bridge'

const P = new THREE.Matrix4()
const PInv = new THREE.Matrix4()
const main = new THREE.Matrix4()
const V = new THREE.Matrix4()
const S = new THREE.Matrix4()

/** M_local = translate(origin) × scale(s, −s, s) × rotateX(90°). */
export function localToMercatorMatrix(): THREE.Matrix4 {
  const origin = MercatorCoordinate.fromLngLat(ORIGIN_LNGLAT, 0)
  const s = origin.meterInMercatorCoordinateUnits()
  return new THREE.Matrix4()
    .makeTranslation(origin.x, origin.y, origin.z)
    .multiply(new THREE.Matrix4().makeScale(s, -s, s))
    .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2))
}

export function syncCamera(camera: THREE.PerspectiveCamera, args: CustomRenderMethodInput, mLocal: THREE.Matrix4) {
  P.fromArray(args.projectionMatrix as ArrayLike<number> as number[])
  PInv.copy(P).invert()
  main.fromArray(args.defaultProjectionData.mainMatrix as ArrayLike<number> as number[])
  V.copy(PInv).multiply(main).multiply(mLocal)
  const e = V.elements
  const k = Math.hypot(e[0], e[1], e[2])

  camera.matrixAutoUpdate = false
  camera.matrixWorldAutoUpdate = false
  camera.matrixWorldInverse.copy(S.makeScale(1 / k, 1 / k, 1 / k)).multiply(V)
  camera.matrixWorld.copy(camera.matrixWorldInverse).invert()
  camera.matrix.copy(camera.matrixWorld)
  camera.matrix.decompose(camera.position, camera.quaternion, camera.scale)
  camera.projectionMatrix.copy(P).multiply(S.makeScale(k, k, k))
  camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert()
  camera.near = args.nearZ / k
  camera.far = args.farZ / k
}

export function createSyncLayer(): CustomLayerInterface {
  const mLocal = localToMercatorMatrix()
  return {
    id: 'three-sync',
    type: 'custom',
    renderingMode: '3d',
    render(_gl, args) {
      const camera = bridge.camera
      if (!camera) return
      syncCamera(camera, args, mLocal)
      const now = performance.now()
      const animating = bridge.columns?.tick(now) ?? false
      advance(now, true)
      if (bridge.columns) useStore.getState().markFirstHexFrame()
      // three.js only draws when MapLibre does: keep frames coming while it animates.
      if (animating) bridge.map?.triggerRepaint()
    },
  }
}
