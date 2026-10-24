import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'
const KEY = 'zynex-theme'
const listeners = new Set<() => void>()

function read(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* storage can be blocked; fall through to the system setting */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.classList.toggle('light', theme === 'light')
}

let current: Theme = typeof window === 'undefined' ? 'light' : read()
if (typeof window !== 'undefined') apply(current)

function commit(theme: Theme) {
  current = theme
  apply(theme)
  try { localStorage.setItem(KEY, theme) } catch { /* not persisted */ }
  listeners.forEach(l => l())
}

/**
 * Switch theme smoothly. Where the browser supports view transitions, the new theme spreads out as a circle from
 * `origin` (the toggle button) over one snapshot of the page, so nothing repaints piece by piece. Elsewhere the
 * colours cross-fade for a moment. Reduced-motion users get an instant switch.
 */
export function setTheme(theme: Theme, origin?: { x: number; y: number }) {
  const root = document.documentElement
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const start = (document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } }).startViewTransition
  if (reduce) { commit(theme); return }
  if (!start) {
    root.classList.add('zx-theme-fade')
    commit(theme)
    window.setTimeout(() => root.classList.remove('zx-theme-fade'), 450)
    return
  }
  const x = origin?.x ?? window.innerWidth - 80
  const y = origin?.y ?? 40
  const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  root.classList.add('zx-theme-vt')
  const vt = start.call(document, () => commit(theme))
  vt.ready.then(() => {
    root.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: 560, easing: 'cubic-bezier(0.32, 0.72, 0, 1)', pseudoElement: '::view-transition-new(root)' },
    )
  }).catch(() => { /* transition skipped: the theme is already applied */ })
  window.setTimeout(() => root.classList.remove('zx-theme-vt'), 700)
}

export function useTheme(): [Theme, (e?: { clientX: number; clientY: number }) => void] {
  const theme = useSyncExternalStore(
    cb => { listeners.add(cb); return () => { listeners.delete(cb) } },
    () => current,
  )
  return [theme, (e?: { clientX: number; clientY: number }) =>
    setTheme(theme === 'dark' ? 'light' : 'dark', e && e.clientX ? { x: e.clientX, y: e.clientY } : undefined)]
}
