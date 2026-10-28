/**
 * three.js scene over the map: warm key light from the northwest, cool sky fill, a shadow-only
 * ground plane, the hex columns, and the High-tier effects (viz-style-guide → Stage;
 * perf-budget → Quality tiers). Depth of field is never used: it would blur only this layer.
 */
import { Bloom, EffectComposer, SMAA, SSAO } from '@react-three/postprocessing'
import { NormalPass, type EffectComposer as EffectComposerImpl } from 'postprocessing'
import { useEffect, useMemo, useRef } from 'react'
import type * as THREE from 'three'
import type { HexData } from '../data/types'
import { HexColumns } from './HexColumns'
import { createNormalMaterial, createUniforms, type HexUniforms } from './hexMaterial'

const SHADOW_EXTENT_M = 380_000

function Effects({ uniforms }: { uniforms: HexUniforms }) {
  const composer = useRef<EffectComposerImpl>(null)
  // The normal pass must see morphed heights: swap its MeshNormalMaterial for the morph-aware one.
  const normalMaterial = useMemo(() => createNormalMaterial(uniforms), [uniforms])

  useEffect(() => {
    const pass = composer.current?.passes.find((p): p is NormalPass => p instanceof NormalPass)
    // `renderPass` is public on NormalPass but missing from its typings.
    if (pass) (pass as unknown as { renderPass: { overrideMaterial: THREE.Material } }).renderPass.overrideMaterial = normalMaterial
  })
  useEffect(() => () => normalMaterial.dispose(), [normalMaterial])

  return (
    <EffectComposer ref={composer} enableNormalPass multisampling={0}>
      <SSAO
        samples={16}
        rings={7}
        radius={0.06}
        intensity={1.2}
        bias={0.03}
        luminanceInfluence={0.6}
        worldDistanceThreshold={60_000}
        worldDistanceFalloff={20_000}
        worldProximityThreshold={4_000}
        worldProximityFalloff={2_000}
      />
      <Bloom luminanceThreshold={1} luminanceSmoothing={0} mipmapBlur intensity={0.8} />
      <SMAA />
    </EffectComposer>
  )
}

export function Scene({ data }: { data: HexData | null }) {
  // One set of morph uniforms, shared by the column, shadow-depth and normal-pass materials.
  const uniforms = useMemo(() => createUniforms(), [])
  return (
    <>
      <hemisphereLight args={['#e3edf7', '#b8ab95', 1.4]} />
      <directionalLight
        position={[-350_000, 450_000, -300_000]}
        intensity={2.2}
        color="#fff1dc"
        castShadow
        shadow-mapSize={[4096, 4096]}
        shadow-camera-left={-SHADOW_EXTENT_M}
        shadow-camera-right={SHADOW_EXTENT_M}
        shadow-camera-top={SHADOW_EXTENT_M}
        shadow-camera-bottom={-SHADOW_EXTENT_M}
        shadow-camera-near={10_000}
        shadow-camera-far={1_500_000}
        shadow-bias={-0.0006}
        shadow-radius={6}
        shadow-blurSamples={12}
      />
      {data && (
        <>
          {/* Shadow-only ground plane: lays column shadows over the map. Mounted with the columns,
              so the map never shows an empty, fully shadowed plane. */}
          <mesh rotation-x={-Math.PI / 2} receiveShadow>
            <planeGeometry args={[2_000_000, 2_000_000]} />
            <shadowMaterial transparent opacity={0.16} />
          </mesh>
          <HexColumns key={data.res} data={data} uniforms={uniforms} />
          <Effects uniforms={uniforms} />
        </>
      )}
    </>
  )
}
