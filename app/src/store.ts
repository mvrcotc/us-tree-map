/** The one shared store (CLAUDE.md → Stack). Per-frame state never goes here (perf-budget). */
import { create } from 'zustand'
import { YEAR_MAX, YEAR_MIN } from './config'
import type { HexData } from './data/types'

export type Tier = 'high' | 'medium' | 'low'

export type AppState = {
  year: number
  selectedH3: string | null
  reducedMotion: boolean
  tier: Tier
  /** Loaded once by the data worker; never mutated. */
  hexData: HexData | null
  /** A load failure the viewer should see (data, outlines or basemap). */
  loadError: string | null
  /** Set once, after the first frame that drew hexes; gates the lazy chart load. */
  firstHexFrame: boolean
  setYear: (year: number) => void
  select: (h3: string | null) => void
  setReducedMotion: (reduced: boolean) => void
  setHexData: (data: HexData) => void
  setLoadError: (message: string) => void
  markFirstHexFrame: () => void
}

const clampYear = (y: number) => Math.min(YEAR_MAX, Math.max(YEAR_MIN, Math.round(y)))

export const useStore = create<AppState>()((set, get) => ({
  year: YEAR_MAX,
  selectedH3: null,
  reducedMotion: false,
  tier: 'high',
  hexData: null,
  loadError: null,
  firstHexFrame: false,
  setYear: (year) => set({ year: clampYear(year) }),
  select: (selectedH3) => set({ selectedH3 }),
  setReducedMotion: (reducedMotion) => set({ reducedMotion }),
  setHexData: (hexData) => set({ hexData }),
  setLoadError: (loadError) => set({ loadError }),
  markFirstHexFrame: () => {
    if (!get().firstHexFrame) set({ firstHexFrame: true })
  },
}))
