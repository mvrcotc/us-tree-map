import { useStore } from '../store'

/** Visible, announced load failure (data, outlines or basemap). */
export function LoadError() {
  const message = useStore((s) => s.loadError)
  if (!message) return null
  return (
    <p role="alert" className="absolute left-1/2 top-16 z-10 -translate-x-1/2 rounded-full bg-surface px-4 py-2 text-sm text-ink-1 shadow-soft">
      {message} Try reloading the page.
    </p>
  )
}
