import { NavLink, Outlet } from 'react-router-dom'
import { UploadSimple, ClockCounterClockwise, Binoculars } from '@phosphor-icons/react'
import './tender.css'

/** Wraps the tender screens. All of its styling is scoped to `.tender-scope`, so the ZYNEX shell is untouched. */
export default function TenderLayout() {
  const tab = ({ isActive }: { isActive: boolean }) => `tender-tab${isActive ? ' is-active' : ''}`

  return (
    <div className="tender-scope" style={{ minHeight: 0 }}>
      <nav className="tender-tabs" aria-label="Tender analysis">
        <NavLink to="/tender" end className={tab}>
          <UploadSimple size={17} style={{ color: "#e07a1f" }} />
          <span>New evaluation</span>
        </NavLink>
        <NavLink to="/tender/history" className={tab}>
          <ClockCounterClockwise size={17} style={{ color: "#014BAA" }} />
          <span>Audit history</span>
        </NavLink>
        <NavLink to="/tender/tiger" className={tab}>
          <Binoculars size={17} style={{ color: "#0f9b8e" }} />
          <span>Tender Tiger</span>
        </NavLink>
      </nav>
      <Outlet />
    </div>
  )
}
