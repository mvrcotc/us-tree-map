/**
 * One ECharts panel, loaded after the first frame with hexes (perf-budget → Baseline).
 * Reads the same store as the map: the marker follows the year slider.
 */
import { LineChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { HexData } from '../data/types'
import { YEAR_MAX, YEAR_MIN } from '../config'
import { useStore } from '../store'

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])

const INK = { primary: '#0b0b0b', secondary: '#52514e', muted: '#898781' }

export default function YearPanel({ data }: { data: HexData }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const year = useStore((s) => s.year)
  const reducedMotion = useStore((s) => s.reducedMotion)
  const [asTable, setAsTable] = useState(false)
  const mean = useMemo(() => Array.from(data.stateMean), [data])

  useEffect(() => {
    if (asTable || !el.current) return
    const c = echarts.init(el.current, undefined, { renderer: 'canvas' })
    chart.current = c
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(el.current)
    return () => {
      ro.disconnect()
      c.dispose()
      chart.current = null
    }
  }, [asTable])

  useEffect(() => {
    chart.current?.setOption({
      animation: !reducedMotion,
      animationDurationUpdate: 500,
      animationEasingUpdate: 'cubicInOut',
      grid: { left: 40, right: 12, top: 12, bottom: 24 },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${Math.round(v * 100)}`, textStyle: { color: INK.primary } },
      xAxis: { type: 'category', data: data.years, axisLabel: { color: INK.secondary, interval: 9 }, axisLine: { lineStyle: { color: INK.muted } } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { color: INK.secondary, formatter: (v: number) => `${Math.round(v * 100)}` }, splitLine: { lineStyle: { color: '#e6e8eb', width: 1 } } },
      series: [
        {
          type: 'line',
          name: 'State mean',
          data: mean,
          symbol: 'none',
          lineStyle: { width: 2, color: '#238b45' },
          markLine: { symbol: 'none', silent: true, label: { color: INK.secondary, formatter: String(year) }, lineStyle: { color: INK.secondary, type: 'solid', width: 1 }, data: [{ xAxis: String(year) }] },
        },
      ],
    })
  }, [asTable, data, mean, year, reducedMotion])

  return (
    <section className="w-80 rounded-2xl bg-surface/95 p-4 shadow-soft">
      <header className="mb-2 flex items-baseline justify-between">
        <h2 className="font-serif text-base text-ink-1">State mean score by year</h2>
        <button type="button" className="rounded-full px-2 py-0.5 text-xs text-ink-2 hover:bg-ink-1/5" onClick={() => setAsTable((t) => !t)} aria-pressed={asTable}>
          {asTable ? 'Show chart' : 'Show as table'}
        </button>
      </header>
      {asTable ? (
        <div className="h-40 overflow-auto text-xs tabular-nums">
          <table className="w-full">
            <thead><tr className="text-left text-ink-2"><th>Year</th><th className="text-right">Score</th></tr></thead>
            <tbody>
              {data.years.map((y, i) => (
                <tr key={y} className={y === year ? 'font-semibold text-ink-1' : 'text-ink-2'}><td>{y}</td><td className="text-right">{Math.round(mean[i] * 100)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={el} className="h-40" role="img" aria-label={`Line chart of the synthetic state mean score, ${YEAR_MIN} to ${YEAR_MAX}; ${year} marked`} />
      )}
      <footer className="mt-2 text-xs text-ink-2">Source: synthetic data (Phase 0 smoke test)</footer>
    </section>
  )
}
