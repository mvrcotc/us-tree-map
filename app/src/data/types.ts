/** Data the worker hands to the stage and charts (typed arrays, transferred once). */
export type HexData = {
  res: number
  count: number
  /** 15-character H3 ids, sorted (instance order = this order). */
  ids: string[]
  lng: Float64Array
  lat: Float64Array
  /** Local-frame center (meters), circumradius and rotation about +y of each hex's projected boundary. */
  x: Float32Array
  z: Float32Array
  radius: Float32Array
  rotation: Float32Array
  years: number[]
  /** count × years.length, row-major by hex. Synthetic in Phase 0. */
  values: Float32Array
  /** Mean value per year over all hexes (typed-array loop in the worker). */
  stateMean: Float32Array
  synthetic: boolean
}

export type WorkerRequest = { id: number; type: 'loadHexes'; res: number }
export type WorkerResponse = { id: number; type: 'hexes'; data: HexData } | { id: number; type: 'error'; message: string }
