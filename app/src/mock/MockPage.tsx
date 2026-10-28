/**
 * /mock: the desktop layout from docs/img/layout.png in the Phase 0 look, for Marco's review.
 * The center is the live stage (synthetic data); every panel is a labeled placeholder with
 * no numbers, so nothing here can be read as data (CLAUDE.md hard rule 1).
 */
import { useState, type ReactNode } from 'react'
import { YEAR_MAX, YEAR_MIN } from '../config'
import { Stage } from '../stage/Stage'
import { useStore } from '../store'
import { GREENS_6 } from '../theme/ramps'
import { LAND_COVER_ORDER, landCover, noData, scoreComponents } from '../theme/tokens'
import { LoadError } from '../ui/LoadError'
import { Overlay } from '../ui/Overlay'

function Panel({ title, children, footer, className = '', badge = false }: { title: string; children: ReactNode; footer?: string; className?: string; badge?: boolean }) {
  return (
    <section className={`flex flex-col rounded-panel bg-surface px-5 py-4 shadow-soft ${className}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-serif text-lg leading-tight text-ink-1">{title}</h2>
        {badge && <Placeholder />}
      </div>
      <div className="mt-2.5 flex-1">{children}</div>
      {footer && <footer className="mt-2.5 border-t border-hairline pt-2 text-xs text-ink-2">{footer}</footer>}
    </section>
  )
}

function Placeholder({ children = 'Placeholder' }: { children?: ReactNode }) {
  return (
    <span className="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-2">{children}</span>
  )
}

function Segmented<T extends string>({ label, options, value, onChange }: { label: string; options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-full bg-surface-muted p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3 py-1 text-sm transition-colors duration-200 ease-calm ${value === o.value ? 'bg-surface text-accent shadow-soft' : 'text-ink-2 hover:text-ink-1'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function TopBar() {
  const [scenario, setScenario] = useState<'rcp45' | 'rcp85'>('rcp45')
  return (
    <header className="flex items-center gap-4 rounded-panel bg-surface px-5 py-3 shadow-soft">
      <div className="mr-auto flex items-baseline gap-3">
        <h1 className="font-serif text-2xl text-ink-1">US Tree Map</h1>
        <span className="text-sm text-ink-2">Wisconsin pilot</span>
      </div>
      <label className="flex w-72 items-center gap-2 rounded-full border border-hairline bg-page px-4 py-2 text-sm text-ink-2">
        <span aria-hidden>⌕</span>
        <input type="search" placeholder="Search a place or ZIP" className="w-full bg-transparent outline-none placeholder:text-ink-2" />
      </label>
      <button type="button" className="rounded-full border border-hairline px-4 py-2 text-sm text-ink-1 hover:bg-surface-muted">
        Metric · <span className="font-medium">Best-species score</span> <span aria-hidden className="text-ink-2">▾</span>
      </button>
      <Segmented
        label="Emissions scenario"
        value={scenario}
        onChange={setScenario}
        options={[
          { value: 'rcp45', label: 'Lower · RCP 4.5' },
          { value: 'rcp85', label: 'Higher · RCP 8.5' },
        ]}
      />
    </header>
  )
}

const WEIGHTS = [
  { key: 'native', label: 'Native' },
  { key: 'climate', label: 'Climate fit' },
  { key: 'pest', label: 'Pest safety' },
  { key: 'need', label: 'Planting need' },
] as const

function LeftColumn() {
  const [when, setWhen] = useState<'past' | 'change' | 'now'>('now')
  const [weights, setWeights] = useState({ native: 1, climate: 1, pest: 1, need: 1 })
  return (
    <div className="flex min-h-0 flex-col gap-4">
      <Panel title="Layers">
        <Segmented
          label="Time frame"
          value={when}
          onChange={setWhen}
          options={[
            { value: 'past', label: 'Past' },
            { value: 'change', label: 'Change' },
            { value: 'now', label: 'Now' },
          ]}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {['Climate', 'Pests'].map((t) => (
            <button key={t} type="button" aria-pressed="false" className="rounded-full border border-hairline px-3 py-1 text-sm text-ink-2 hover:bg-surface-muted">
              {t}
            </button>
          ))}
          <button type="button" disabled title="Waiting on Tree Equity Score permission (decision D7)" className="cursor-not-allowed rounded-full border border-dashed border-hairline px-3 py-1 text-sm text-ink-2">
            Need
          </button>
        </div>
      </Panel>
      <Panel title="Engine weights" className="flex-1" footer="A screening tool, not planting advice. Every species shows its reasons.">
        <div className="flex flex-col gap-4">
          {WEIGHTS.map((w) => {
            const disabled = w.key === 'need'
            return (
              <label key={w.key} className={`flex flex-col gap-1 text-sm ${disabled ? 'text-ink-2' : 'text-ink-2'}`}>
                <span className="flex justify-between">
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden className="size-2.5 rounded-full" style={{ background: scoreComponents[w.key] }} />
                    {w.label}
                  </span>
                  <span className="tabular-nums">{disabled ? 'hidden' : `${weights[w.key].toFixed(2)}×`}</span>
                </span>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.25}
                  value={weights[w.key]}
                  disabled={disabled}
                  onChange={(e) => setWeights((s) => ({ ...s, [w.key]: Number(e.target.value) }))}
                />
                {disabled && <span className="text-xs">Hidden until American Forests approves Tree Equity Score use.</span>}
              </label>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}

function Legend() {
  return (
    <div className="pointer-events-auto absolute bottom-4 left-4 rounded-control bg-surface/95 p-3 shadow-soft">
      <p className="text-xs font-medium text-ink-1">Best-species score</p>
      <p className="text-[11px] text-ink-2">Height + color · synthetic data</p>
      <div className="mt-2 flex items-end gap-1">
        {GREENS_6.map((c, i) => (
          <div key={c} className="flex flex-col items-center gap-1">
            <span className="block h-3 w-7 rounded-sm" style={{ background: c }} />
            <span className="text-[10px] tabular-nums text-ink-2">{Math.round((i * 100) / 6)}</span>
          </div>
        ))}
        <div className="ml-2 flex flex-col items-center gap-1">
          <span className="block h-3 w-7 rounded-sm border" style={{ background: noData.fill, borderColor: noData.outline }} />
          <span className="text-[10px] text-ink-2">No data</span>
        </div>
      </div>
    </div>
  )
}

const BAR_WIDTHS = [92, 82, 73, 64]
const SEGMENT_SPLIT = [0.3, 0.28, 0.27, 0.15]

function RightColumn() {
  return (
    <div className="flex min-h-0 flex-col gap-4">
      <Panel title="Best species here" badge footer="Source: species engine (Phase 3)">
        <p className="mb-2 text-xs text-ink-2">Click a hex to rank species</p>
        <ul className="flex flex-col gap-2" aria-label="Placeholder species bars">
          {BAR_WIDTHS.map((w, i) => (
            <li key={i}>
              <span className="mb-1 block h-1.5 w-24 rounded bg-surface-muted" />
              <span className="flex h-2.5 gap-[2px]" style={{ width: `${w}%` }}>
                {Object.values(scoreComponents).map((c, j) => (
                  <span key={c} className="h-full rounded-sm opacity-80" style={{ background: c, width: `${SEGMENT_SPLIT[j] * 100}%` }} />
                ))}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-2">
          {Object.entries(scoreComponents).map(([k, c]) => (
            <span key={k} className="inline-flex items-center gap-1">
              <span className="size-2 rounded-full" style={{ background: c }} />
              {k}
            </span>
          ))}
        </div>
      </Panel>
      <Panel title="Pest threats" badge footer="Source: Potter et al. 2019; IDS; NAPIS (pending)">
        <div className="grid grid-cols-6 gap-1" aria-label="Placeholder pest grid">
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} className="h-5 rounded bg-surface-muted" />
          ))}
        </div>
      </Panel>
      <Panel title="Past vs. now" badge className="flex-1" footer="Source: LANDFIRE BpS; Annual NLCD (pending)">
        {['Past', 'Now'].map((label) => (
          <div key={label} className="mb-2 flex items-center gap-3 text-xs text-ink-2">
            <span className="w-8">{label}</span>
            <span className="flex h-3 flex-1 gap-[2px]">
              {LAND_COVER_ORDER.map((k) => (
                <span key={k} className="h-full flex-1 rounded-sm opacity-80" style={{ background: landCover.light[k] }} />
              ))}
            </span>
          </div>
        ))}
      </Panel>
    </div>
  )
}

const LC_LABELS: Record<(typeof LAND_COVER_ORDER)[number], string> = { forest: 'Forest', grass: 'Grass / pasture', crop: 'Cropland', developed: 'Developed', other: 'Other' }

function LandCoverPanel() {
  // Five even placeholder bands with 2 px gaps and direct labels (viz-style-guide → Chart categories).
  const band = 19
  return (
    <Panel title="Land cover through time" badge footer="Source: Annual NLCD Collection 1.2, 1985–2025 (pending)">
      <div className="flex items-start gap-4">
        <svg viewBox="0 0 560 110" preserveAspectRatio="none" className="h-24 flex-1" role="img" aria-label="Placeholder stacked area chart">
          {LAND_COVER_ORDER.map((k, i) => {
            // Gently sloped bands, 2 px apart: a shape placeholder, not data.
            const top = (x: number) => 110 - (i + 1) * (band + 2) - Math.sin((x / 560) * Math.PI) * (2 + i)
            const xs = [0, 140, 280, 420, 560]
            const d = `M0,${110 - i * (band + 2)} ` + xs.map((x) => `L${x},${top(x)}`).join(' ') + ` L560,${110 - i * (band + 2)} Z`
            return <path key={k} d={d} fill={landCover.light[k]} opacity={0.75} />
          })}
        </svg>
        <ul className="flex flex-col gap-1 pt-1 text-xs text-ink-2">
          {[...LAND_COVER_ORDER].reverse().map((k) => (
            <li key={k} className="inline-flex items-center gap-2">
              <span className="size-2.5 rounded-sm" style={{ background: landCover.light[k] }} />
              {LC_LABELS[k]}
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  )
}

function TimePanel() {
  const year = useStore((s) => s.year)
  const setYear = useStore((s) => s.setYear)
  return (
    <Panel title="Time" footer="Projection: Tree Atlas, 2070–2099 (no 2050 step, decision D1)">
      <div className="flex items-center gap-4">
        <button type="button" aria-label="Play" className="grid size-12 shrink-0 place-items-center rounded-full bg-accent text-white shadow-soft hover:brightness-110">
          <span aria-hidden className="ml-0.5">▶</span>
        </button>
        <div className="flex-1">
          <div className="flex items-baseline justify-between">
            <span className="font-serif text-3xl tabular-nums text-ink-1">{year}</span>
            <span className="text-xs text-ink-2">synthetic</span>
          </div>
          <input type="range" min={YEAR_MIN} max={YEAR_MAX} value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year" aria-valuetext={String(year)} className="mt-1 w-full" />
          <div className="mt-1 flex justify-between text-xs text-ink-2">
            <span>Pre-settlement (not yet available)</span>
            <span>{YEAR_MIN} – {YEAR_MAX}</span>
            <span>2070 – 2099 (not yet available)</span>
          </div>
        </div>
      </div>
    </Panel>
  )
}

export default function MockPage() {
  return (
    <div className="grid h-full grid-cols-[280px_minmax(0,1fr)_320px] grid-rows-[auto_minmax(0,1fr)_auto] gap-4 bg-page p-4">
      <div className="col-span-3">
        <TopBar />
      </div>
      <LeftColumn />
      <section className="relative min-h-0 overflow-hidden rounded-panel shadow-soft" aria-label="3D map">
        <Stage />
        <Overlay />
        <LoadError />
        <p className="pointer-events-none absolute left-4 top-4 rounded-full bg-surface/90 px-3 py-1 text-xs font-medium text-ink-2 shadow-soft" data-testid="synthetic-label">
          Synthetic data · Phase 0 mock
        </p>
        <Legend />
      </section>
      <RightColumn />
      <div className="col-span-3 grid grid-cols-[minmax(0,1fr)_420px] gap-4">
        <LandCoverPanel />
        <TimePanel />
      </div>
    </div>
  )
}
