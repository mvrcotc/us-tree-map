import type { HexData, WorkerResponse } from './types'

const worker = new Worker(new URL('./data.worker.ts', import.meta.url), { type: 'module' })

// Each request carries an id, so overlapping requests (res 5, 6, 7) never take each other's answers.
let nextId = 0
const pending = new Map<number, { resolve: (d: HexData) => void; reject: (e: Error) => void }>()

worker.addEventListener('message', (e: MessageEvent<WorkerResponse>) => {
  const request = pending.get(e.data.id)
  if (!request) return
  pending.delete(e.data.id)
  if (e.data.type === 'error') request.reject(new Error(e.data.message))
  else request.resolve(e.data.data)
})

const cache = new Map<number, Promise<HexData>>()

/** Load one resolution's hexes once; later calls share the same promise. */
export function loadHexes(res: number): Promise<HexData> {
  let result = cache.get(res)
  if (!result) {
    const id = nextId++
    result = new Promise<HexData>((resolve, reject) => pending.set(id, { resolve, reject }))
    worker.postMessage({ id, type: 'loadHexes', res })
    cache.set(res, result)
  }
  return result
}
