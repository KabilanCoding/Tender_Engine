import { Link } from 'react-router-dom'
import { ArrowRight, ClipboardList } from 'lucide-react'

export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6 max-w-[1100px]">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Library</span>
          <h1 className="mt-1">Reports</h1>
          <p>Estimation and tender reports you generate are collected here for later reference.</p>
        </div>
      </div>
      <div className="zx-empty">
        <div className="zx-empty-icon"><ClipboardList size={28} strokeWidth={1.5} /></div>
        <h2>No reports yet</h2>
        <p>Tender eligibility reports live under Tender Analysis, in the audit history. Reports generated from here will appear in this list.</p>
        <div className="zx-actions">
          <Link to="/tender/history" className="zx-action primary">Open audit history <ArrowRight size={14} /></Link>
          <Link to="/estimation" className="zx-action">Start an estimate</Link>
        </div>
      </div>
    </div>
  )
}
