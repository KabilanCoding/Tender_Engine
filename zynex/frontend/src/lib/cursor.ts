/**
 * Cursor: the system arrow is hidden and replaced by a royal dot, with a faint royal glow around it and a short trail of
 * dots that fades behind fast moves.
 * Only on devices with a mouse, never with "reduce motion". Decoration only: it ignores clicks and stops when idle.
 */
const TRAIL = 8

export function startCursor() {
  if (typeof window === 'undefined') return
  if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return

  const layer = document.createElement('div')
  layer.className = 'zx-cursor'
  layer.setAttribute('aria-hidden', 'true')
  const glow = document.createElement('i')
  glow.className = 'zx-cursor-glow'
  layer.appendChild(glow)
  const dots = Array.from({ length: TRAIL }, () => {
    const d = document.createElement('i')
    d.className = 'zx-cursor-dot'
    layer.appendChild(d)
    return { el: d, x: 0, y: 0 }
  })
  const lead = document.createElement('i')
  lead.className = 'zx-cursor-lead'
  layer.appendChild(lead)
  document.body.appendChild(layer)
  document.documentElement.classList.add('zx-own-cursor')

  let mx = 0, my = 0, gx = 0, gy = 0, raf = 0, idle = 0
  const place = (el: HTMLElement, x: number, y: number) => { el.style.transform = `translate3d(${x}px, ${y}px, 0)` }

  const step = () => {
    gx += (mx - gx) * 0.18; gy += (my - gy) * 0.18
    place(glow, gx, gy)
    let px = mx, py = my, moving = Math.hypot(mx - gx, my - gy) > 0.5
    dots.forEach((t, i) => {
      t.x += (px - t.x) * 0.45; t.y += (py - t.y) * 0.45
      place(t.el, t.x, t.y)
      const far = Math.hypot(mx - t.x, my - t.y)
      t.el.style.opacity = String(Math.min(1, far / 60) * (1 - i / TRAIL) * 0.55)
      if (far > 0.5) moving = true
      px = t.x; py = t.y
    })
    idle = moving ? 0 : idle + 1
    raf = idle > 30 ? 0 : requestAnimationFrame(step)   // stop drawing once everything has settled
  }

  window.addEventListener('pointermove', e => {
    mx = e.clientX; my = e.clientY
    lead.style.transform = `translate3d(${mx}px, ${my}px, 0)`   // the dot itself follows exactly, without lag
    layer.classList.add('is-on')
    if (!raf) { idle = 0; raf = requestAnimationFrame(step) }
  }, { passive: true })
  document.addEventListener('pointerleave', () => layer.classList.remove('is-on'))
  window.addEventListener('blur', () => layer.classList.remove('is-on'))
}
