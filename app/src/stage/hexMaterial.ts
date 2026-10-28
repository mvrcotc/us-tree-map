/**
 * Column materials. Heights and colors morph in the vertex shader between per-instance
 * `from` and `to` attributes with one uniform `uT` (perf-budget → Rendering rules).
 *
 * The same morph runs in three materials so every pass sees the same geometry:
 * the lit column material, the shadow depth material, and the normal pass that SSAO reads.
 * Column tops output the exact ramp color, unlit and without tone mapping
 * (viz-style-guide → True data colors); shading lives on the sides.
 */
import * as THREE from 'three'

export type HexUniforms = {
  uT: { value: number }
  uRise: { value: number }
  uSelected: { value: number }
  uSelGlow: { value: number }
}

export const createUniforms = (): HexUniforms => ({
  uT: { value: 1 },
  uRise: { value: 1e9 },
  uSelected: { value: -1 },
  uSelGlow: { value: 0.9 },
})

/** Duration of the intro rise per column and the west → east stagger (viz-style-guide → Motion). */
export const RISE_MS = 600
export const RISE_STAGGER_MS = 600
export const SELECTED_LIFT = 0.04

const MORPH_PARS = /* glsl */ `
attribute float aFrom;
attribute float aTo;
attribute vec3 aColorFrom;
attribute vec3 aColorTo;
attribute float aDelay;
attribute float aHex;
uniform float uT;
uniform float uRise;
uniform float uSelected;
float hexEaseInOut(float t) { return t < 0.5 ? 4.0 * t * t * t : 1.0 - pow(-2.0 * t + 2.0, 3.0) / 2.0; }
float hexEaseOut(float t) { return 1.0 - pow(1.0 - t, 3.0); }
float hexIsSelected() {
#ifdef USE_INSTANCING
  return float(gl_InstanceID == int(uSelected));
#else
  return 0.0;
#endif
}
float hexHeight() {
  float h = mix(aFrom, aTo, hexEaseInOut(clamp(uT, 0.0, 1.0)));
  h *= hexEaseOut(clamp((uRise - aDelay) / ${RISE_MS.toFixed(1)}, 0.0, 1.0));
  h *= 1.0 + ${SELECTED_LIFT.toFixed(2)} * hexIsSelected();
  return max(h, 1.0);
}
`

/** Scale the unit prism's y by the morphed height; non-hex meshes (aHex = 0) pass through. */
const MORPH_VERTEX = /* glsl */ `
#include <begin_vertex>
transformed.y = mix(transformed.y, transformed.y * hexHeight(), aHex);
`

function injectMorph(shader: THREE.WebGLProgramParametersWithUniforms, uniforms: HexUniforms) {
  Object.assign(shader.uniforms, uniforms)
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', `#include <common>\n${MORPH_PARS}`)
    .replace('#include <begin_vertex>', MORPH_VERTEX)
}

export function createColumnMaterial(uniforms: HexUniforms): THREE.MeshLambertMaterial {
  const material = new THREE.MeshLambertMaterial({ color: 0xffffff, toneMapped: false })
  material.onBeforeCompile = (shader) => {
    injectMorph(shader, uniforms)
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vHexColor;\nvarying float vTop;\nvarying float vSel;')
      .replace(
        MORPH_VERTEX,
        `${MORPH_VERTEX}\nvHexColor = mix(aColorFrom, aColorTo, hexEaseInOut(clamp(uT, 0.0, 1.0)));\nvTop = step(0.5, normal.y);\nvSel = hexIsSelected();`,
      )
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vHexColor;\nvarying float vTop;\nvarying float vSel;\nuniform float uSelGlow;')
      .replace('vec4 diffuseColor = vec4( diffuse, opacity );', 'vec4 diffuseColor = vec4( vHexColor, opacity );')
      .replace(
        '#include <tonemapping_fragment>',
        // True data color on tops; only the selected hex goes above 1.0 so bloom picks it alone.
        'if ( vTop > 0.5 ) gl_FragColor = vec4( vHexColor * ( 1.0 + uSelGlow * vSel ), 1.0 );\n#include <tonemapping_fragment>',
      )
  }
  material.customProgramCacheKey = () => 'hex-columns'
  return material
}

export function createDepthMaterial(uniforms: HexUniforms): THREE.MeshDepthMaterial {
  const material = new THREE.MeshDepthMaterial()
  material.onBeforeCompile = (shader) => injectMorph(shader, uniforms)
  material.customProgramCacheKey = () => 'hex-depth'
  return material
}

/**
 * Replacement for postprocessing's NormalPass material (a MeshNormalMaterial, which would
 * ignore the morph). Outputs view-space normals packed like MeshNormalMaterial.
 */
export function createNormalMaterial(uniforms: HexUniforms): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: { ...uniforms },
    vertexShader: /* glsl */ `
      #include <common>
      ${MORPH_PARS}
      varying vec3 vViewNormal;
      void main() {
        vec3 transformed = vec3( position );
        transformed.y = mix(transformed.y, transformed.y * hexHeight(), aHex);
        vec4 local = vec4( transformed, 1.0 );
        vec3 n = normal;
        #ifdef USE_INSTANCING
          local = instanceMatrix * local;
          n = mat3( instanceMatrix ) * n;
        #endif
        vViewNormal = normalize( normalMatrix * n );
        gl_Position = projectionMatrix * modelViewMatrix * local;
      }`,
    fragmentShader: /* glsl */ `
      #include <packing>
      varying vec3 vViewNormal;
      void main() {
        gl_FragColor = vec4( packNormalToRGB( normalize( vViewNormal ) ), 1.0 );
      }`,
  })
}
