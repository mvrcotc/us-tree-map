import { YEAR_MAX, YEAR_MIN } from '../config'
import { useStore } from '../store'

export function YearSlider() {
  const year = useStore((s) => s.year)
  const setYear = useStore((s) => s.setYear)
  return (
    <label className="flex items-center gap-3 text-sm text-ink-2">
      <span className="font-medium text-ink-1">Year</span>
      <input
        type="range"
        min={YEAR_MIN}
        max={YEAR_MAX}
        step={1}
        value={year}
        onChange={(e) => setYear(Number(e.target.value))}
        aria-valuetext={String(year)}
        className="w-64 accent-accent"
      />
      <output className="w-12 font-serif text-lg tabular-nums text-ink-1">{year}</output>
    </label>
  )
}
