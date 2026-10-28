/** App-wide constants. Data paths follow the data contract (`v{N}/hex/{table}/r{res}/{p3}.parquet`). */

export const DATA_BASE: string = import.meta.env.VITE_DATA_BASE ?? '/data'
export const DATA_VERSION = 1
export const dataUrl = (path: string) => `${DATA_BASE}/v${DATA_VERSION}/${path}`

export const PILOT_NAME = 'Wisconsin'

/** Fixed origin of the three.js local frame (meters; x east, y up, z south). Near the state's center. */
export const ORIGIN_LNGLAT: [number, number] = [-89.9, 44.8]

/** Annual NLCD years; the synthetic smoke data uses the same range. */
export const YEAR_MIN = 1985
export const YEAR_MAX = 2024

/** Tallest column, in meters, at the state view. */
export const MAX_COLUMN_M = 30_000

export const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
