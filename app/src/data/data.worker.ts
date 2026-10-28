/// <reference lib="webworker" />
/**
 * Data worker: reads Parquet with hyparquet (CLAUDE.md → Stack), places hexes in the local
 * frame, and computes chart aggregates as typed-array loops, off the main thread.
 */
import { cellToBoundary, cellToLatLng } from 'h3-js'
import { decompress as zstd } from 'fzstd'
import { parquetReadObjects, type Compressors } from 'hyparquet'
import { dataUrl, ORIGIN_LNGLAT, YEAR_MAX, YEAR_MIN } from '../config'
import { localFrame } from '../geo/mercator'
import { syntheticValue } from './synthetic'
import type { HexData, WorkerRequest, WorkerResponse } from './types'

// The data contract writes ZSTD; hyparquet's core reads only Snappy.
const compressors: Compressors = { ZSTD: (input, outputLength) => zstd(input, new Uint8Array(outputLength)) }

type Manifest = { files: Record<string, { table: string; res: number | null }> }

async function readHexIds(res: number): Promise<string[]> {
  const manifest: Manifest = await fetch(dataUrl('manifest.json')).then((r) => r.json())
  const paths = Object.entries(manifest.files)
    .filter(([, f]) => f.table === 'hex_base' && f.res === res)
    .map(([path]) => path)
  const parts = await Promise.all(
    paths.map(async (path) => {
      const file = await fetch(dataUrl(path)).then((r) => r.arrayBuffer())
      const rows = (await parquetReadObjects({ file, columns: ['h3'], compressors })) as { h3: bigint }[]
      return rows.map((r) => r.h3.toString(16))
    }),
  )
  return parts.flat().sort()
}

function buildHexData(ids: string[], res: number): HexData {
  const n = ids.length
  const frame = localFrame(ORIGIN_LNGLAT)
  const years: number[] = []
  for (let y = YEAR_MIN; y <= YEAR_MAX; y++) years.push(y)
  const ny = years.length

  const lng = new Float64Array(n)
  const lat = new Float64Array(n)
  const x = new Float32Array(n)
  const z = new Float32Array(n)
  const radius = new Float32Array(n)
  const rotation = new Float32Array(n)
  const values = new Float32Array(n * ny)
  const stateMean = new Float32Array(ny)

  for (let i = 0; i < n; i++) {
    const [clat, clng] = cellToLatLng(ids[i])
    lat[i] = clat
    lng[i] = clng
    const [cx, cz] = frame.toLocal(clng, clat)
    x[i] = cx
    z[i] = cz
    const boundary = cellToBoundary(ids[i])
    let r = 0
    for (const [blat, blng] of boundary) {
      const [bx, bz] = frame.toLocal(blng, blat)
      r += Math.hypot(bx - cx, bz - cz)
    }
    radius[i] = r / boundary.length
    const [vx, vz] = frame.toLocal(boundary[0][1], boundary[0][0])
    rotation[i] = Math.atan2(vx - cx, vz - cz)
    for (let j = 0; j < ny; j++) {
      const v = syntheticValue(ids[i], clng, clat, years[j])
      values[i * ny + j] = v
      stateMean[j] += v / n
    }
  }
  return { res, count: n, ids, lng, lat, x, z, radius, rotation, years, values, stateMean, synthetic: true }
}

self.onmessage = async (e: MessageEvent<WorkerRequest>) => {
  const { id } = e.data
  try {
    if (e.data.type === 'loadHexes') {
      const data = buildHexData(await readHexIds(e.data.res), e.data.res)
      const transfer = [data.lng, data.lat, data.x, data.z, data.radius, data.rotation, data.values, data.stateMean].map((a) => a.buffer)
      self.postMessage({ id, type: 'hexes', data } satisfies WorkerResponse, transfer)
    }
  } catch (err) {
    self.postMessage({ id, type: 'error', message: String(err) } satisfies WorkerResponse)
  }
}
