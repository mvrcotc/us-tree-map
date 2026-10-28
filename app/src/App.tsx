import { lazy, Suspense, useEffect } from 'react'
import { PILOT_NAME } from './config'
import { Stage } from './stage/Stage'
import { useStore } from './store'
import { Overlay } from './ui/Overlay'
import { YearSlider } from './ui/YearSlider'

// ECharts loads after the first frame with hexes (perf-budget: keeps it off the critical path).
const YearPanel = lazy(() => import('./charts/YearPanel'))

function useReducedMotion() {
  const setReducedMotion = useStore((s) => s.setReducedMotion)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const onChange = () => setReducedMotion(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [setReducedMotion])
}

function hasWebGL2() {
  try {
    return Boolean(document.createElement('canvas').getContext('webgl2'))
  } catch {
    return false
  }
}

export default function App() {
  useReducedMotion()
  const firstHexFrame = useStore((s) => s.firstHexFrame)
  const hexData = useStore((s) => s.hexData)

  if (!hasWebGL2()) {
    return <main className="grid h-full place-items-center p-8 text-ink-1">This map needs WebGL 2. The flat 2D mode comes in a later phase.</main>
  }

  return (
    <main className="relative h-full w-full overflow-hidden bg-page">
      <Stage />
      <Overlay />
      <header className="pointer-events-none absolute left-4 top-4 flex flex-col gap-2">
        <h1 className="font-serif text-2xl text-ink-1">US Tree Map · {PILOT_NAME}</h1>
        <p className="w-fit rounded-full bg-surface/90 px-3 py-1 text-xs font-medium text-ink-2 shadow-soft" data-testid="synthetic-label">
          Synthetic data · Phase 0 smoke test, not real values
        </p>
      </header>
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-surface/95 px-5 py-3 shadow-soft">
        <YearSlider />
      </div>
      {firstHexFrame && hexData && (
        <div className="absolute right-4 top-4">
          <Suspense fallback={null}>
            <YearPanel data={hexData} />
          </Suspense>
        </div>
      )}
    </main>
  )
}
