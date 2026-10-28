import { lazy, Suspense } from 'react'
import { useReducedMotion } from '../ui/useReducedMotion'

// /mock: the layout mock for Marco's review (Phase 0, step 8). No router dependency for one route.
const MockPage = lazy(() => import('./MockPage'))

export function MockRoute() {
  useReducedMotion()
  return (
    <Suspense fallback={null}>
      <MockPage />
    </Suspense>
  )
}
