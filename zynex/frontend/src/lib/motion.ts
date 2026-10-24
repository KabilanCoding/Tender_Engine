/**
 * App-wide motion helpers, started once from main.tsx.
 *  - spotlight: cards get --mx/--my so a soft light follows the cursor (one listener, rAF-throttled)
 *  - count-up: big figures (.zx-stat-value, .zx-ring-total, .summary-value) count from 0 when they appear
 */
const CARD = '.zx-kpi, .zx-panel, .zx-proj, .zx-stat-card, .zx-run-row, .bg-white.rounded-2xl, .bg-white.rounded-xl'

export function startMotion() {
  if (typeof window === 'undefined') return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  let raf = 0, last: PointerEvent | null = null
  window.addEventListener('pointermove', e => {
    last = e
    if (raf) return
    raf = requestAnimationFrame(() => {
      raf = 0
      const el = (last?.target as Element | null)?.closest?.(CARD) as HTMLElement | null
      if (!el || !last) return
      const r = el.getBoundingClientRect()
      el.style.setProperty('--mx', `${last.clientX - r.left}px`)
      el.style.setProperty('--my', `${last.clientY - r.top}px`)
    })
  }, { passive: true })

  if (reduce) return
  const seen = new WeakSet<Element>()
  const count = (el: HTMLElement) => {
    const node = el.firstChild
    if (!node || node.nodeType !== Node.TEXT_NODE || el.childNodes.length !== 1) return
    const m = (node.nodeValue || '').match(/^(\D*)(\d+(?:\.\d+)?)(.*)$/)
    if (!m || seen.has(el)) return
    seen.add(el)
    const [, pre, num, post] = m, target = parseFloat(num), dec = (num.split('.')[1] || '').length
    if (!target) return
    const t0 = performance.now(), dur = 900
    let shown = `${pre}${(0).toFixed(dec)}${post}`
    node.nodeValue = shown
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / dur), v = target * (1 - Math.pow(1 - p, 3))
      // write into React's own text node, and stop if React has since changed it
      if (node.nodeValue !== shown) return
      shown = `${pre}${(p < 1 ? v : target).toFixed(dec)}${post}`
      node.nodeValue = shown
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }
  const scan = () => document.querySelectorAll<HTMLElement>('.zx-stat-value, .summary-value').forEach(el => {
    count(el)
  })
  new MutationObserver(() => requestAnimationFrame(scan)).observe(document.body, { childList: true, subtree: true })
}
