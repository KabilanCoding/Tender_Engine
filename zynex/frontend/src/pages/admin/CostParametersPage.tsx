import { useEffect, useState } from 'react'
import { Code2, Palette, Server, ShieldCheck, Briefcase, Users, IndianRupee, Percent, Info, Save, Loader } from 'lucide-react'
import { kbApi, type CostParameter } from '../../api/knowledgeBase'

const ROLE_LOOK: Record<string, { icon: typeof Code2; color: string }> = {
  developer: { icon: Code2, color: '#014BAA' }, designer: { icon: Palette, color: '#c2410c' }, devops: { icon: Server, color: '#0f766e' },
  qa: { icon: ShieldCheck, color: '#1F7A56' }, manager: { icon: Briefcase, color: '#7c5c12' },
}
const FIELDS = [
  { f: 'hourly_rate', label: 'Rate', unit: '₹/hr' }, { f: 'qa_percentage', label: 'QA', unit: '%' },
  { f: 'devops_percentage', label: 'DevOps', unit: '%' }, { f: 'contingency_percentage', label: 'Contingency', unit: '%' },
  { f: 'profit_margin_percentage', label: 'Profit', unit: '%' },
] as const

export default function CostParametersPage() {
  const [rows, setRows] = useState<CostParameter[]>([])
  const [editing, setEditing] = useState<Record<number, Partial<CostParameter>>>({})
  const [saving, setSaving] = useState<number | null>(null)

  useEffect(() => { kbApi.listCostParams().then(r => setRows(r.data)) }, [])

  function edit(id: number, field: keyof CostParameter, value: string) {
    setEditing(e => ({ ...e, [id]: { ...e[id], [field]: parseFloat(value) || 0 } }))
  }

  async function save(row: CostParameter) {
    const changes = editing[row.id]
    if (!changes) return
    setSaving(row.id)
    try {
      const { data } = await kbApi.updateCostParam(row.id, changes)
      setRows(r => r.map(x => x.id === data.id ? data : x))
      setEditing(e => { const n = { ...e }; delete n[row.id]; return n })
    } finally {
      setSaving(null)
    }
  }

  function val(row: CostParameter, field: keyof CostParameter): string {
    const override = editing[row.id]?.[field]
    return String(override !== undefined ? override : row[field])
  }

  const avg = rows.length ? rows.reduce((t, r) => t + Number(r.hourly_rate || 0), 0) / rows.length : 0
  const roles = new Set(rows.map(r => r.role)).size
  const profit = rows.length ? rows.reduce((t, r) => t + Number(r.profit_margin_percentage || 0), 0) / rows.length : 0
  const dirty = Object.keys(editing).length

  return (
    <div className="flex flex-col gap-6 max-w-[1200px]">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Pricing</span>
          <h1 className="mt-1">Cost Parameters</h1>
          <p>Hourly rates and overheads used by every cost estimate. Edit a value, then save that row.</p>
        </div>
        {dirty > 0 && <span className="zx-chip is-warn">{dirty} unsaved row{dirty > 1 ? 's' : ''}</span>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { icon: Users, label: 'Roles priced', value: String(roles), hint: `${rows.length} role and level rows`, accent: '#014BAA' },
          { icon: IndianRupee, label: 'Average rate', value: `₹${avg.toFixed(0)}`, hint: 'per hour, across all rows', accent: '#0f766e' },
          { icon: Percent, label: 'Average profit margin', value: `${profit.toFixed(0)}%`, hint: 'added on top of cost', accent: '#1F7A56' },
        ].map(c => (
          <div key={c.label} className="zx-stat-card" style={{ ['--accent' as string]: c.accent }}>
            <div className="zx-stat-icon"><c.icon size={20} /></div>
            <div>
              <div className="zx-stat-value">{c.value}</div>
              <div className="zx-stat-label">{c.label}</div>
              <div className="zx-stat-hint">{c.hint}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl border overflow-hidden">
        <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[860px]">
          <thead className="bg-gray-50 text-gray-500 text-[11px] uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">Role</th>
              {FIELDS.map(h => (
                <th key={h.f} className="px-3 py-3 text-left font-semibold">{h.label} <span className="normal-case tracking-normal text-gray-400 font-normal">({h.unit})</span></th>
              ))}
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-gray-500">
                  No cost parameters yet. Run the seed script to load the default rates.
                </td>
              </tr>
            )}
            {rows.map(row => {
              const isDirty = !!editing[row.id]
              const look = ROLE_LOOK[row.role?.toLowerCase()] ?? { icon: Users, color: '#64748b' }
              const Icon = look.icon
              return (
                <tr key={row.id} className={`border-t border-gray-100 transition-colors ${isDirty ? 'bg-amber-50' : 'hover:bg-gray-50'}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="w-9 h-9 rounded-xl grid place-items-center flex-shrink-0"
                        style={{ color: look.color, background: `color-mix(in srgb, ${look.color} 13%, transparent)`, border: `1px solid color-mix(in srgb, ${look.color} 25%, transparent)` }}>
                        <Icon size={16} />
                      </span>
                      <div>
                        <p className="font-semibold text-gray-800 capitalize">{row.role === 'qa' ? 'QA' : row.role === 'devops' ? 'DevOps' : row.role}</p>
                        <p className="text-xs text-gray-500 capitalize">{row.level}</p>
                      </div>
                    </div>
                  </td>
                  {FIELDS.map(({ f, unit }) => (
                    <td key={f} className="px-3 py-2">
                      <label className="relative flex items-center">
                        {unit !== '%' && <span className="absolute left-2.5 text-xs text-gray-400 pointer-events-none">₹</span>}
                        <input
                          type="number"
                          value={val(row, f)}
                          onChange={e => edit(row.id, f, e.target.value)}
                          className={`w-24 border border-gray-200 rounded-lg py-1.5 text-sm tabular-nums bg-transparent text-gray-800 focus:outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-500/10 transition ${unit === '%' ? 'pl-2.5 pr-6' : 'pl-6 pr-2'}`}
                          step="0.5"
                          min="0"
                          aria-label={`${row.role} ${row.level} ${f.replace(/_/g, ' ')}`}
                        />
                        {unit === '%' && <span className="absolute left-[4.6rem] text-xs text-gray-400 pointer-events-none">%</span>}
                      </label>
                    </td>
                  ))}
                  <td className="px-4 py-3 text-right">
                    {isDirty && (
                      <button
                        onClick={() => save(row)}
                        disabled={saving === row.id}
                        className="zx-action primary disabled:opacity-50"
                        style={{ padding: '0.4rem 0.85rem' }}
                      >
                        {saving === row.id ? <><Loader size={13} className="animate-spin" /> Saving…</> : <><Save size={13} /> Save</>}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-2xl border p-4 text-sm" style={{ background: 'var(--brand-tint)', borderColor: 'var(--line)', color: 'var(--ink-2)' }}>
        <Info size={16} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--brand-blue)' }} />
        <p>Changes apply to new cost estimates. Reports that were already generated keep the rates they were made with.</p>
      </div>
    </div>
  )
}
