import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import Lenis from 'lenis'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  SquaresFour as LayoutDashboard,
  ChartLineUp as BarChart2,
  FileMagnifyingGlass as FileSearch,
  Article as FileText,
  Buildings as Database,
  FolderOpen,
  ClipboardText as ClipboardList,
  SignOut as LogOut,
  MagnifyingGlass as Search,
  GearSix as Settings,
  Sun,
  Moon,
  ShieldCheck,
  MagnifyingGlass,
  CaretLeft,
  CaretRight,
  UploadSimple,
  ClockCounterClockwise,
  Binoculars,
  CurrencyInr,
} from '@phosphor-icons/react'
import { useAuthStore } from '../../store/authStore'
import { fetchSettings } from '../../store/settingsStore'
import { useTheme } from '../../lib/theme'
import UserAvatar from '../icons/UserAvatar'
import CommandPalette, { type PaletteItem } from './CommandPalette'
import ActiveRunDock from './ActiveRunDock'
import AssistantLauncher from './AssistantLauncher'
import { useAiStatus } from '../common/AiStatusBadge'
import { kbApi } from '../../api/knowledgeBase'

const topNav = [
  { to: '/dashboard',  label: 'Dashboard',          icon: LayoutDashboard, accent: 'var(--brand-blue)' },
  { to: '/tender',     label: 'Tender Analysis',     icon: FileSearch, accent: '#e07a1f' },
  { to: '/proposals',  label: 'Proposal Generator',  icon: FileText, accent: '#2f6fde' },
  { to: '/estimation', label: 'Project Estimation',  icon: BarChart2, accent: '#0f9b8e' },
]

const sideNav = [
  { group: 'Company', items: [
    { to: '/knowledge-base', label: 'Knowledge Base',   icon: Database, accent: 'var(--brand-blue)' },
    { to: '/kb-search',      label: 'KB Search',        icon: Search, accent: '#0f9b8e' },
  ] },
  { group: 'Records', items: [
    { to: '/past-projects',  label: 'Past Projects',    icon: FolderOpen, accent: '#e07a1f' },
    { to: '/reports',        label: 'Reports',          icon: ClipboardList, accent: '#4f9a2c' },
  ] },
  { group: 'Admin', items: [
    { to: '/settings',       label: 'Settings',         icon: Settings, accent: '#5b6b8a' },
  ] },
]

// Pages that manage their own full-bleed layout (no outer padding, no outer scroll)
const FULL_BLEED = ['/estimation', '/kb-search']

/** Position of the active item inside a container, for a highlight pill that glides between items. */
function useActiveRect(container: React.RefObject<HTMLElement>, deps: unknown[]) {
  const [rect, setRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  useLayoutEffect(() => {
    const el = container.current
    if (!el) return
    const measure = () => {
      const a = el.querySelector<HTMLElement>('.is-active')
      setRect(a ? { x: a.offsetLeft, y: a.offsetTop, w: a.offsetWidth, h: a.offsetHeight } : null)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  return rect
}

const SIDE_KEY = 'zynex-side-collapsed'

export default function AppShell() {
  // the screens read the server-side settings (default model, limits, prompts) from a local copy
  useEffect(() => { fetchSettings().catch(() => { /* defaults are used until the next load */ }) }, [])
  const { fullName, role, logout } = useAuthStore()
  const [theme, toggleTheme] = useTheme()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const isFullBleed = FULL_BLEED.some(p => pathname.startsWith(p))
  const mainRef = useRef<HTMLElement>(null)
  const tabsRef = useRef<HTMLElement>(null)
  const sideRef = useRef<HTMLElement>(null)
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem(SIDE_KEY) !== '0' } catch { return true } })   // closed until the user opens it; their choice is remembered
  const tabRect = useActiveRect(tabsRef, [pathname])
  const sideRect = useActiveRect(sideRef, [pathname, collapsed])
  const ai = useAiStatus()
  const [company, setCompany] = useState<string | null>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)

  useEffect(() => {
    kbApi.getProfile().then(r => {
      const fields = r.data.sections.flatMap(x => x.fields)
      const f = fields.find(x => x.key === 'trade_name_short_name' && x.value) ?? fields.find(x => x.key === 'company_legal_name')
      if (f?.value) setCompany(String(f.value))
    }).catch(() => { /* not allowed for this role: the card shows a generic title */ })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen(v => !v) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function toggleSide() {
    setCollapsed(v => { const n = !v; try { localStorage.setItem(SIDE_KEY, n ? '1' : '0') } catch { /* not saved */ } return n })
  }

  const paletteItems: PaletteItem[] = [
    ...topNav.map(n => ({ to: n.to, label: n.label, group: 'Main', icon: n.icon, accent: n.accent })),
    { to: '/tender', label: 'New tender evaluation', group: 'Tender Analysis', icon: UploadSimple, accent: '#e07a1f', keywords: 'upload analyse rfp' },
    { to: '/tender/history', label: 'Audit history', group: 'Tender Analysis', icon: ClockCounterClockwise, accent: '#e07a1f', keywords: 'runs reports verdict' },
    { to: '/tender/tiger', label: 'Tender Tiger', group: 'Tender Analysis', icon: Binoculars, accent: '#e07a1f', keywords: 'notices deadlines' },
    ...sideNav.flatMap(g => g.items.map(n => ({ to: n.to, label: n.label, group: g.group, icon: n.icon, accent: n.accent }))),
    { to: '/cost-parameters', label: 'Cost parameters', group: 'Admin', icon: CurrencyInr, accent: '#4f9a2c', keywords: 'rates pricing' },
  ]

  // momentum scrolling for the page area (not for full-bleed screens, which scroll their own panels)
  useEffect(() => {
    const el = mainRef.current
    if (!el || isFullBleed || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const lenis = new Lenis({
      wrapper: el, content: el.firstElementChild as HTMLElement,
      duration: 1.15, easing: t => 1 - Math.pow(1 - t, 3), smoothWheel: true,   // ease-out cubic: a softer start than quartic, so wheel ticks blend into one glide
      allowNestedScroll: true,   // tables and panels with their own scroll keep it
    })
    let raf = requestAnimationFrame(function loop(time) { lenis.raf(time); raf = requestAnimationFrame(loop) })
    return () => { cancelAnimationFrame(raf); lenis.destroy() }
  }, [isFullBleed, pathname])

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <a href="#main" className="skip-link">Skip to content</a>

      {/* ── Floating header: brand, main sections, theme, user ── */}
      <header className="zx-island">
        <div className="zx-island-inner">
          <div className="zx-brand-wrap" title="Zero-Cloud · Your-Data · Neural Estimation & eXecution">
            <img
              src="/zynex-logo.png"
              alt="ZYNEX"
              className="zx-brand-logo"
              onError={(e) => {
                // hide the image if the logo is not found
                (e.target as HTMLImageElement).style.display = 'none'
              }}
            />
            <span className="zx-brand">ZYNEX</span>
          </div>

          <nav className="zx-tabs" aria-label="Main" ref={tabsRef}>
            {tabRect && <span className="zx-glider" aria-hidden="true" style={{ transform: `translateX(${tabRect.x}px)`, width: tabRect.w, height: tabRect.h, top: tabRect.y }} />}
            {topNav.map(({ to, label, icon: Icon, accent }) => (
              <NavLink key={to} to={to} title={label} style={{ ['--accent' as string]: accent }} className={({ isActive }) => `zx-tab${isActive ? ' is-active' : ''}`}>
                <Icon size={17} />
                <span className="zx-tab-label">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2 min-w-fit">
            <div className="zx-user" title={`${fullName ?? 'User'} · ${role ?? ''}`}>
              <UserAvatar size={34} />
              <span className="hidden md:flex flex-col leading-tight pr-2">
                <span className="zx-user-name">{fullName ?? 'User'}</span>
                <span className="zx-user-role">{role === 'admin' && <ShieldCheck size={11} weight="fill" />}{role}</span>
              </span>
            </div>
            <button
              onClick={toggleTheme}
              className="zx-icon-btn"
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? <Sun size={17} weight="fill" style={{ color: '#fbbf24' }} /> : <Moon size={17} style={{ color: 'var(--brand-blue)' }} />}
            </button>
            <button onClick={handleLogout} className="zx-icon-btn" title="Log out" aria-label="Log out">
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Sidebar */}
        <aside className={`zx-side ${collapsed ? 'is-collapsed' : ''}`} aria-label="Library and settings" ref={sideRef}>
          <div className="zx-workspace">
            <span className="zx-workspace-mark"><img src="/xenovex-mark.png" alt="" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} /></span>
            <span className="zx-workspace-text">
              <b title={company ?? undefined}>{company ?? 'Company workspace'}</b>
              <span>Company workspace</span>
            </span>
          </div>

          <button type="button" className="zx-side-handle" onClick={toggleSide} aria-label={collapsed ? 'Expand the side menu' : 'Collapse the side menu'} title={collapsed ? 'Expand menu' : 'Collapse menu'}>
            {collapsed ? <CaretRight size={13} weight="bold" /> : <CaretLeft size={13} weight="bold" />}
          </button>
          {sideRect && <span className="zx-side-glider" aria-hidden="true" style={{ transform: `translateY(${sideRect.y}px)`, height: sideRect.h, left: sideRect.x, width: sideRect.w }} />}
          {sideNav.map(({ group, items }) => (
            <div key={group} className="zx-side-group">
              <p className="zx-side-heading">{group}</p>
              {items.map(({ to, label, icon: Icon, accent }) => (
                <NavLink
                  key={to}
                  to={to}
                  style={{ ['--accent' as string]: accent }}
                  title={label}
                  aria-label={label}
                  className={({ isActive }) => `zx-side-link${isActive ? ' is-active' : ''}`}
                >
                  <span className="zx-side-icon"><Icon size={17} className="shrink-0" /></span>
                  <span className="zx-label">{label}</span>
                </NavLink>
              ))}
            </div>
          ))}

          <div className="zx-ai-card" role="status" title={ai.detail} style={{ ['--tone' as string]: ai.tone }}>
            <span className="zx-ai-dot" aria-hidden="true" />
            <span className="zx-ai-text">
              <b>{ai.label}</b>
              <span>{ai.detail}</span>
            </span>
          </div>
          <button type="button" className="zx-side-logout" onClick={handleLogout} title="Log out" style={{ ['--accent' as string]: '#d64545' }}>
            <span className="zx-side-icon"><LogOut size={17} /></span>
            <span className="zx-label">Log out</span>
          </button>
          <p className="zx-side-foot">Runs on your own servers · data stays on this network</p>
        </aside>

        {/* Main content */}
        <main
          id="main"
          ref={mainRef}
          tabIndex={-1}
          className={`flex-1 min-w-0 ${isFullBleed ? 'p-0 overflow-hidden' : 'p-3 sm:p-5 overflow-auto'}`}
          style={{ outline: 'none' }}
        >
          {/* keyed by section only, so moving between tabs of one section keeps its state */}
          <div key={pathname.split('/')[1]} className={`zx-route ${isFullBleed ? 'h-full' : ''}`}>
            <Outlet />
          </div>
        </main>
      </div>
      <ActiveRunDock />
      <AssistantLauncher />
      <CommandPalette items={paletteItems} open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
