import { beforeEach, describe, expect, it } from 'vitest'
import { YEAR_MAX, YEAR_MIN } from './config'
import { useStore } from './store'

const initial = useStore.getState()

describe('store', () => {
  beforeEach(() => useStore.setState(initial, true))

  it('starts at the latest year with nothing selected', () => {
    const s = useStore.getState()
    expect(s.year).toBe(YEAR_MAX)
    expect(s.selectedH3).toBeNull()
    expect(s.firstHexFrame).toBe(false)
  })

  it('clamps and rounds the year to the data range', () => {
    const { setYear } = useStore.getState()
    setYear(1700)
    expect(useStore.getState().year).toBe(YEAR_MIN)
    setYear(3000)
    expect(useStore.getState().year).toBe(YEAR_MAX)
    setYear(2001.6)
    expect(useStore.getState().year).toBe(2002)
  })

  it('notifies subscribers once per change', () => {
    const years: number[] = []
    const unsubscribe = useStore.subscribe((s, prev) => s.year !== prev.year && years.push(s.year))
    useStore.getState().setYear(1990)
    useStore.getState().setYear(1990)
    useStore.getState().setYear(1991)
    unsubscribe()
    expect(years).toEqual([1990, 1991])
  })

  it('selects and clears a hex', () => {
    useStore.getState().select('862a1072fffffff')
    expect(useStore.getState().selectedH3).toBe('862a1072fffffff')
    useStore.getState().select(null)
    expect(useStore.getState().selectedH3).toBeNull()
  })

  it('marks the first hex frame only once', () => {
    let changes = 0
    const unsubscribe = useStore.subscribe((s, prev) => s.firstHexFrame !== prev.firstHexFrame && changes++)
    useStore.getState().markFirstHexFrame()
    useStore.getState().markFirstHexFrame()
    unsubscribe()
    expect(useStore.getState().firstHexFrame).toBe(true)
    expect(changes).toBe(1)
  })
})
