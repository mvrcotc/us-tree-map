/**
 * The stage: a MapLibre street map that owns the camera and all input, and a transparent
 * three.js canvas on top (pointer-events: none, frameloop "never") drawn from MapLibre's
 * custom layer (CLAUDE.md → Gotchas → Map + 3D layer sync).
 */
import { Canvas } from '@react-three/fiber'
import { Map as MLMap, setWorkerUrl, type LngLatBoundsLike } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type * as THREE from 'three'
import { BASEMAP_STYLE, dataUrl } from '../config'
import { loadHexes } from '../data/client'
import { useStore } from '../store'
import { bridge } from './bridge'
import { createSyncLayer } from './mapSync'
import { Scene } from './Scene'
import { installTestHooks } from './testHooks'

setWorkerUrl(workerUrl)

const FLY_PITCH = 50
const FLY_ZOOM = 9.5

type FeatureCollection = { features: { geometry: { coordinates: unknown } }[] }

function bboxOf(fc: FeatureCollection): LngLatBoundsLike {
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity]
  const walk = (c: unknown): void => {
    if (typeof (c as number[])[0] === 'number') {
      const [x, y] = c as number[]
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y)
    } else (c as unknown[]).forEach(walk)
  }
  fc.features.forEach((f) => walk(f.geometry.coordinates))
  return [[w, s], [e, n]]
}

export function Stage() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const hexData = useStore((s) => s.hexData)

  useEffect(() => {
    if (!useStore.getState().hexData) loadHexes(6).then(useStore.getState().setHexData).catch((err) => console.error(err))
  }, [])

  useEffect(() => {
    const map = new MLMap({
      container: mapContainer.current!,
      style: BASEMAP_STYLE,
      center: [-89.9, 44.8],
      zoom: 5.8,
      pitch: 45,
      bearing: -8,
      maxPitch: 85,
      attributionControl: { compact: true },
    })
    bridge.map = map

    map.on('load', async () => {
      const [state, counties] = await Promise.all([
        fetch(dataUrl('geo/state.json')).then((r) => r.json()),
        fetch(dataUrl('geo/counties.json')).then((r) => r.json()),
      ])
      map.addSource('counties', { type: 'geojson', data: counties })
      map.addSource('state', { type: 'geojson', data: state })
      map.addLayer({ id: 'county-lines', type: 'line', source: 'counties', paint: { 'line-color': '#9aa7b4', 'line-width': 0.5, 'line-opacity': 0.6 } })
      map.addLayer({ id: 'state-outline', type: 'line', source: 'state', paint: { 'line-color': '#4f5d6b', 'line-width': 1.2 } })
      map.addLayer(createSyncLayer())
      const reduced = useStore.getState().reducedMotion
      map.fitBounds(bboxOf(state), { padding: 60, pitch: 45, bearing: -8, duration: reduced ? 0 : 1200 })
    })

    map.on('click', (e) => {
      const columns = bridge.columns
      if (!columns) return
      const i = columns.pick(e.point.x, e.point.y)
      if (i < 0) return
      useStore.getState().select(columns.ids[i])
      const center = columns.lngLat(i)
      // Reduced motion: jump, don't fly. Never pass `essential: true` (CLAUDE.md → Gotchas).
      if (useStore.getState().reducedMotion) map.jumpTo({ center, zoom: FLY_ZOOM, pitch: FLY_PITCH })
      else map.flyTo({ center, zoom: FLY_ZOOM, pitch: FLY_PITCH, duration: 1500 })
    })

    if (new URLSearchParams(location.search).has('test')) installTestHooks()

    return () => {
      bridge.map = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    bridge.map?.triggerRepaint()
  }, [hexData])

  return (
    <div className="absolute inset-0">
      {/* MapLibre's CSS makes its container position: relative, so it sits inside a sized wrapper. */}
      <div className="absolute inset-0">
        <div ref={mapContainer} className="h-full w-full" data-testid="map" />
      </div>
      <div className="pointer-events-none absolute inset-0">
        <Canvas
          frameloop="never"
          flat
          shadows="variance"
          dpr={[1, 2]}
          gl={{ alpha: true, antialias: false, powerPreference: 'high-performance' }}
          camera={{ manual: true }}
          style={{ pointerEvents: 'none' }}
          onCreated={({ gl, camera }) => {
            gl.setClearColor(0x000000, 0)
            bridge.camera = camera as THREE.PerspectiveCamera
            camera.matrixAutoUpdate = false
            camera.matrixWorldAutoUpdate = false
            bridge.map?.triggerRepaint()
          }}
        >
          <Scene data={hexData} />
        </Canvas>
      </div>
    </div>
  )
}
