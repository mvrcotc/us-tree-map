/**
 * Web Mercator helpers matching MapLibre's `MercatorCoordinate` (same earth radius),
 * so the worker can place hexes without loading MapLibre.
 */

const EARTH_RADIUS = 6371008.8
const EARTH_CIRCUMFERENCE = 2 * Math.PI * EARTH_RADIUS

export const mercatorX = (lng: number) => (180 + lng) / 360
export const mercatorY = (lat: number) =>
  (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360

/** Meters → Mercator units at a latitude (MapLibre's `meterInMercatorCoordinateUnits`). */
export const meterInMercatorUnits = (lat: number) => 1 / EARTH_CIRCUMFERENCE / Math.cos((lat * Math.PI) / 180)

/** A frame in meters around a fixed origin: x east, z south (CLAUDE.md → map + 3D layer sync). */
export function localFrame([lng0, lat0]: [number, number]) {
  const ox = mercatorX(lng0)
  const oy = mercatorY(lat0)
  const s = meterInMercatorUnits(lat0)
  return {
    ox,
    oy,
    s,
    toLocal(lng: number, lat: number): [number, number] {
      return [(mercatorX(lng) - ox) / s, (mercatorY(lat) - oy) / s]
    },
  }
}
