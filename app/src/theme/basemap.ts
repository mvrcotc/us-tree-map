/**
 * OpenFreeMap Positron, muted toward the UI palette (viz-style-guide → Stage → Street map):
 * soft roads and water, light labels, and a faint map at the state view that comes forward
 * as you zoom into a city. The attribution stays (MapLibre shows it from the style's sources).
 */
import type { LayerSpecification, StyleSpecification } from 'maplibre-gl'

const COLORS = {
  background: '#f1f3f5',
  water: '#d5dee6',
  waterway: '#c7d3de',
  green: '#e8ece9',
  residential: '#eceef0',
  building: '#e7eaed',
  boundary: '#b4bec8',
  placeLabel: '#56606a',
  regionLabel: '#8a939c',
  roadLabel: '#7d868f',
  waterLabel: '#6a7f99',
  halo: '#f7f9fa',
}

/** Opacity that rises from `low` at the state view (z ≤ from) to 1 at city zoom (z ≥ to). */
const comeForward = (low: number, from = 7, to = 11) => ['interpolate', ['linear'], ['zoom'], from, low, to, 1]

function mute(layer: LayerSpecification): LayerSpecification {
  const l = structuredClone(layer) as LayerSpecification & { paint?: Record<string, unknown>; 'source-layer'?: string }
  const paint = (l.paint ??= {})
  const src = l['source-layer']

  switch (l.type) {
    case 'background':
      paint['background-color'] = COLORS.background
      break
    case 'fill':
      if (src === 'water') paint['fill-color'] = COLORS.water
      else if (l.id === 'park' || l.id === 'landcover_wood') {
        paint['fill-color'] = COLORS.green
        paint['fill-opacity'] = comeForward(0.3, 8, 12)
      } else if (l.id === 'landuse_residential') {
        paint['fill-color'] = COLORS.residential
        paint['fill-opacity'] = comeForward(0.2, 8, 12)
      } else if (src === 'building') {
        paint['fill-color'] = COLORS.building
        paint['fill-outline-color'] = COLORS.residential
      }
      break
    case 'line':
      if (src === 'waterway') paint['line-color'] = COLORS.waterway
      else if (src === 'transportation' || src === 'aeroway') paint['line-opacity'] = comeForward(0.25)
      else if (src === 'boundary') {
        paint['line-color'] = COLORS.boundary
        paint['line-opacity'] = 0.7
      }
      break
    case 'symbol': {
      const isRegion = l.id.startsWith('label_country') || l.id === 'label_state'
      const isRoad = src === 'transportation_name'
      const isWater = src === 'water_name' || src === 'waterway'
      paint['text-color'] = isWater ? COLORS.waterLabel : isRoad ? COLORS.roadLabel : isRegion ? COLORS.regionLabel : COLORS.placeLabel
      paint['text-halo-color'] = COLORS.halo
      paint['text-opacity'] = isRoad ? comeForward(0, 9, 12) : comeForward(0.55, 6, 10)
      if (isRoad) paint['icon-opacity'] = comeForward(0, 9, 12)
      break
    }
  }
  return l
}

export function mutedPositron(style: StyleSpecification): StyleSpecification {
  return { ...style, layers: style.layers.map(mute) }
}
