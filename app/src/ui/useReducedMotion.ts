import { useEffect } from 'react'
import { useStore } from '../store'

/** Mirrors `prefers-reduced-motion` into the store (viz-style-guide → Motion). */
export function useReducedMotion() {
  const setReducedMotion = useStore((s) => s.setReducedMotion)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const onChange = () => setReducedMotion(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [setReducedMotion])
}
