import { describe, expect, it } from 'vitest'
import { localFrame, mercatorX, mercatorY, meterInMercatorUnits } from './mercator'

describe('mercator (matches MapLibre MercatorCoordinate)', () => {
  it('maps lng/lat to unit Mercator', () => {
    expect(mercatorX(-180)).toBe(0)
    expect(mercatorX(0)).toBe(0.5)
    expect(mercatorY(0)).toBeCloseTo(0.5, 12)
  })

  it('uses MapLibre’s meter scale (value from MapLibre’s own test at null island)', () => {
    expect(meterInMercatorUnits(0)).toBeCloseTo(2.4981121214570498e-8, 20)
  })

  it('local frame: origin at 0, x east, z south, in meters', () => {
    const f = localFrame([-89.9, 44.8])
    expect(f.toLocal(-89.9, 44.8)).toEqual([0, 0])
    const [xEast] = f.toLocal(-89.8, 44.8)
    const [, zSouth] = f.toLocal(-89.9, 44.7)
    expect(xEast).toBeGreaterThan(7_800) // 0.1° of longitude ≈ 7.9 km at 44.8°N
    expect(xEast).toBeLessThan(8_000)
    expect(zSouth).toBeGreaterThan(11_000) // 0.1° of latitude ≈ 11.1 km
    expect(zSouth).toBeLessThan(11_200)
  })
})
