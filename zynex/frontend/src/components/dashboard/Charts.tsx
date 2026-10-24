/**
 * Dashboard charts, drawn in plain SVG so they theme with the CSS tokens and need no chart library.
 * Colours come from CSS variables (validated for colour-blind separation in light and dark separately):
 *   --c-series-1 / --c-series-2  two-series trend  ·  --s-ok / --s-warn / --s-bad  verdict status  ·  --c-mag  single-hue magnitude
 */
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'

/* measure a container's width so SVG charts can draw at real pixel size (crisp 2px lines, no stretching) */
function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/* monotone cubic path through points: smooth, never overshoots below zero */
function smoothPath(pts: [number, number][]): string {
  if (pts.length < 2) return pts.length ? `M${pts[0][0]},${pts[0][1]}` : ''
  const n = pts.length
  const dx = (i: number) => pts[i + 1][0] - pts[i][0]
  const s = (i: number) => (pts[i + 1][1] - pts[i][1]) / dx(i)
  const m: number[] = new Array(n)
  m[0] = s(0); m[n - 1] = s(n - 2)
  for (let i = 1; i < n - 1; i++) {
    const a = s(i - 1), b = s(i)
    m[i] = a * b <= 0 ? 0 : (2 * a * b) / (a + b)   // harmonic mean: flat at peaks and valleys, no overshoot
  }
  let d = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 0; i < n - 1; i++) {
    const h = dx(i) / 3
    d += ` C${pts[i][0] + h},${pts[i][1] + m[i] * h} ${pts[i + 1][0] - h},${pts[i + 1][1] - m[i + 1] * h} ${pts[i + 1][0]},${pts[i + 1][1]}`
  }
  return d
}

function niceMax(v: number): { max: number; step: number } {
  const peak = Math.max(1, v)
  const step = peak <= 4 ? 1 : Math.ceil(peak / 4)
  return { max: Math.ceil(peak / step) * step, step }
}

/* ── Trend: two series over time, area under the first, crosshair + tooltip ───────────────── */
export interface TrendSeries { key: string; label: string; values: number[]; color: string }

export function TrendChart({ labels, series, height = 210, ariaLabel }: {
  labels: string[]; series: TrendSeries[]; height?: number; ariaLabel: string
}) {
  const [ref, w] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const gid = useId().replace(/:/g, '')
  const pad = { l: 28, r: 12, t: 12, b: 26 }
  const iw = Math.max(0, w - pad.l - pad.r), ih = height - pad.t - pad.b
  const { max, step } = niceMax(Math.max(...series.flatMap(s => s.values)))
  const n = labels.length
  const x = (i: number) => pad.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw)
  const y = (v: number) => pad.t + ih - (v / max) * ih
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step)

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    const i = Math.round(((e.clientX - r.left) / r.width) * (n - 1))
    setHover(Math.max(0, Math.min(n - 1, i)))
  }

  return (
    <div ref={ref} className="zx-trend" style={{ height }} role="img" aria-label={ariaLabel}>
      {w > 0 && (
        <svg width={w} height={height} className="block overflow-visible">
          <defs>
            <linearGradient id={`${gid}a`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={series[0].color} stopOpacity="0.28" />
              <stop offset="1" stopColor={series[0].color} stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map(t => (
            <g key={t}>
              <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} className="zx-grid-line" />
              <text x={pad.l - 8} y={y(t)} dy="0.32em" textAnchor="end" className="zx-axis-text">{t}</text>
            </g>
          ))}
          {labels.map((l, i) => (i % 2 === 1 || i === n - 1) && (
            <text key={i} x={x(i)} y={height - 6} textAnchor="middle" className="zx-axis-text">{l}</text>
          ))}
          {/* area + line for the first series, line only for the rest */}
          <path className="zx-trend-area" d={`${smoothPath(series[0].values.map((v, i) => [x(i), y(v)]))} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={`url(#${gid}a)`} />
          {series.map(s => (
            <path key={s.key} className="zx-trend-line" d={smoothPath(s.values.map((v, i) => [x(i), y(v)]))} stroke={s.color} />
          ))}
          {hover !== null && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + ih} className="zx-crosshair" />
              {series.map(s => <circle key={s.key} cx={x(hover)} cy={y(s.values[hover])} r="5" fill={s.color} className="zx-trend-dot" />)}
            </g>
          )}
          <rect x={pad.l} y={pad.t} width={iw} height={ih} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
      )}
      {hover !== null && w > 0 && (
        <div className="zx-tip zx-tip-float" style={{ left: Math.min(Math.max(x(hover), 90), w - 90), top: 0 }} role="tooltip">
          <p className="zx-tip-title">{labels[hover]}</p>
          {series.map(s => (
            <p key={s.key} className="zx-tip-row"><i className="zx-swatch" style={{ background: s.color }} /><span>{s.label}</span><b>{s.values[hover]}</b></p>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Radial rings: share of each verdict, one concentric ring per category ─────────────────── */
export interface RingItem { key: string; label: string; value: number; color: string }

export function RadialRings({ items, total, centerLabel }: { items: RingItem[]; total: number; centerLabel: string }) {
  const [shown, setShown] = useState(false)
  useEffect(() => { const t = requestAnimationFrame(() => setShown(true)); return () => cancelAnimationFrame(t) }, [])
  const size = 176, c = size / 2, sw = 11, gap = 6
  return (
    <div className="flex flex-col items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
        aria-label={items.map(i => `${i.label} ${i.value} of ${total}`).join(', ')}>
        {items.map((it, k) => {
          const r = c - sw / 2 - k * (sw + gap)
          const C = 2 * Math.PI * r
          const frac = total ? it.value / total : 0
          return (
            <g key={it.key} transform={`rotate(-90 ${c} ${c})`}>
              <circle cx={c} cy={c} r={r} fill="none" className="zx-ring-track" strokeWidth={sw} />
              <circle cx={c} cy={c} r={r} fill="none" stroke={it.color} strokeWidth={sw} strokeLinecap="round"
                strokeDasharray={`${shown ? frac * C : 0} ${C}`} className="zx-ring-arc" opacity={frac > 0 ? 1 : 0}
                style={{ transitionDelay: `${k * 90}ms` }} />
            </g>
          )
        })}
        <text x={c} y={c - 4} textAnchor="middle" className="zx-ring-total">{total}</text>
        <text x={c} y={c + 16} textAnchor="middle" className="zx-axis-text">{centerLabel}</text>
      </svg>
      <ul className={`grid ${items.length === 4 ? "grid-cols-2" : "grid-cols-3"} gap-2 w-full`}>
        {items.map(it => (
          <li key={it.key} className="zx-ring-key">
            <i className="zx-swatch" style={{ background: it.color }} />
            <div className="min-w-0">
              <p className="text-[11px] leading-tight" style={{ color: 'var(--ink-3)' }}>{it.label}</p>
              <p className="text-sm font-semibold tabular-nums" style={{ color: 'var(--ink)' }}>
                {it.value} <span className="text-xs font-normal" style={{ color: 'var(--ink-3)' }}>· {total ? Math.round((it.value / total) * 100) : 0}%</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ── Columns: one value per bucket, single hue, value printed on top ───────────────────────── */
export function Columns({ items, height = 150, highlight }: {
  items: { label: string; value: number; hint?: string }[]; height?: number; highlight?: number
}) {
  const [hover, setHover] = useState<number | null>(null)
  const { max } = niceMax(Math.max(...items.map(i => i.value)))
  return (
    <div className="zx-columns" style={{ height }} role="img" aria-label={items.map(i => `${i.label}: ${i.value}`).join(', ')}>
      {items.map((it, i) => (
        <div key={i} className="zx-columns-col" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <span className="zx-columns-value">{it.value}</span>
          <div className="zx-columns-track">
            <div className={`zx-columns-bar ${i === highlight ? 'is-hi' : ''}`} style={{ height: `${(it.value / max) * 100}%` }} />
          </div>
          <span className="zx-columns-label">{it.label}</span>
          {hover === i && it.hint && <div className="zx-tip" role="tooltip" style={{ bottom: '100%' }}><p className="zx-tip-title">{it.hint}</p></div>}
        </div>
      ))}
    </div>
  )
}

/* ── Horizontal bars: ranked categories, single hue, value at the end ──────────────────────── */
export function HBars({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(1, ...items.map(i => i.value))
  return (
    <ul className="space-y-3">
      {items.map(it => (
        <li key={it.label}>
          <div className="flex items-baseline justify-between gap-3 text-xs mb-1.5">
            <span className="truncate" style={{ color: 'var(--ink-2)' }} title={it.label}>{it.label}</span>
            <b className="tabular-nums" style={{ color: 'var(--ink)' }}>{it.value}</b>
          </div>
          <div className="zx-hbar-track"><div className="zx-hbar" style={{ width: `${(it.value / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  )
}

/* ── Sparkline for stat tiles ──────────────────────────────────────────────────────────────── */
export function Sparkline({ values, color = 'var(--accent)', width = 96, height = 30 }: {
  values: number[]; color?: string; width?: number; height?: number
}) {
  const gid = useId().replace(/:/g, '')
  const max = Math.max(1, ...values)
  const pts = values.map((v, i) => [ (i / Math.max(1, values.length - 1)) * width, height - 3 - (v / max) * (height - 6) ] as [number, number])
  const d = smoothPath(pts)
  return (
    <svg width={width} height={height} className="zx-spark" aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.3" /><stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${width},${height} L0,${height} Z`} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}
