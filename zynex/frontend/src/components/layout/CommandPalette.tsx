import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { MagnifyingGlass, ArrowElbowDownLeft, ArrowUp, ArrowDown } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'

export interface PaletteItem { to: string; label: string; group: string; icon: Icon; accent?: string; keywords?: string }

/** Quick jump to any screen: Ctrl/Cmd+K opens it, type to filter, arrows to move, Enter to go. */
export default function CommandPalette({ items, open, onClose }: { items: PaletteItem[]; open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return items
    return items.filter(it => `${it.label} ${it.group} ${it.keywords ?? ''}`.toLowerCase().includes(t))
  }, [q, items])

  useEffect(() => { if (open) { setQ(''); setI(0); requestAnimationFrame(() => input.current?.focus()) } }, [open])
  useEffect(() => { setI(0) }, [q])

  if (!open) return null

  function go(it?: PaletteItem) {
    if (!it) return
    onClose()
    navigate(it.to)
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setI(v => Math.min(shown.length - 1, v + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setI(v => Math.max(0, v - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(shown[i]) }
    else if (e.key === 'Escape') { e.preventDefault(); onClose() }
  }

  const groups = [...new Set(shown.map(s => s.group))]
  return createPortal(
    <div className="zx-cmd-backdrop" onMouseDown={onClose} role="presentation">
      <div className="zx-cmd" role="dialog" aria-modal="true" aria-label="Go to a screen" onMouseDown={e => e.stopPropagation()} onKeyDown={onKey}>
        <label className="zx-cmd-search">
          <MagnifyingGlass size={18} aria-hidden="true" />
          <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Go to a screen…" aria-label="Search screens" />
          <kbd>Esc</kbd>
        </label>
        <div className="zx-cmd-list" role="listbox" aria-label="Screens">
          {shown.length === 0 && <p className="zx-cmd-empty">Nothing matches “{q}”.</p>}
          {groups.map(g => (
            <div key={g}>
              <p className="zx-cmd-group">{g}</p>
              {shown.filter(s => s.group === g).map(it => {
                const idx = shown.indexOf(it)
                const Icon = it.icon
                return (
                  <button key={it.to} type="button" role="option" aria-selected={idx === i}
                    className={`zx-cmd-item ${idx === i ? 'is-on' : ''}`} onMouseEnter={() => setI(idx)} onClick={() => go(it)}>
                    <span className="zx-cmd-icon" style={{ ['--accent' as string]: it.accent ?? 'var(--brand-blue)' }}><Icon size={17} /></span>
                    <span className="flex-1 text-left">{it.label}</span>
                    {idx === i && <ArrowElbowDownLeft size={14} className="opacity-60" />}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        <div className="zx-cmd-foot">
          <span><kbd><ArrowUp size={10} /></kbd><kbd><ArrowDown size={10} /></kbd> move</span>
          <span><kbd><ArrowElbowDownLeft size={10} /></kbd> open</span>
          <span><kbd>Ctrl</kbd><kbd>K</kbd> anywhere</span>
        </div>
      </div>
    </div>,
    document.body,
  )
}
