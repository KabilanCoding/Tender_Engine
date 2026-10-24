import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, DollarSign, Landmark, Pencil, Plus, Trash2 } from 'lucide-react'
import { kbApi, type FinancialYear } from '../../../api/knowledgeBase'
import { Loading, Panel, RecordModal, dateText, fyLabel, inrShort, useConfirm, type FieldDef } from './ui'
import { ProfileForm, type ProfileState } from './ProfileForm'

const FIELDS: FieldDef[] = [
  { key: 'fiscal_year', label: 'Financial year ends in', type: 'number', required: true, mono: true, hint: 'The year the financial year ends: 2025 means FY 2024-25 (April 2024 to March 2025).' },
  { key: 'annual_turnover', label: 'Annual turnover (INR)', type: 'number', required: true, mono: true },
  { key: 'net_profit', label: 'Net profit after tax (INR)', type: 'number', mono: true },
  { key: 'net_worth', label: 'Net worth (INR)', type: 'number', mono: true },
  { key: 'working_capital', label: 'Working capital (INR)', type: 'number', mono: true },
  { key: 'ebitda', label: 'EBITDA (INR)', type: 'number', mono: true },
  { key: 'gross_assets', label: 'Gross assets (INR)', type: 'number', mono: true },
  { key: 'total_liabilities', label: 'Total liabilities (INR)', type: 'number', mono: true },
  { key: 'current_ratio', label: 'Current ratio', type: 'number', mono: true },
  { key: 'audit_firm', label: 'Auditor', type: 'text' },
  { key: 'audit_signoff_date', label: 'Audit sign-off date', type: 'date' },
  { key: 'notes', label: 'Notes', type: 'textarea' },
]

/** The financial year that has just been completed (the Indian year ends 31 March). */
function completedFy(today = new Date()): number {
  return today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
}

export default function FinancialsPanel({ profile }: { profile: ProfileState }) {
  const [rows, setRows] = useState<FinancialYear[] | null>(null)
  const [editing, setEditing] = useState<Partial<FinancialYear> | null>(null)
  const confirm = useConfirm()
  const load = () => kbApi.listFinancials().then(r => setRows(r.data))
  useEffect(() => { load() }, [])

  const latest = rows?.[0]
  const last3 = useMemo(() => (rows ?? []).slice(0, 3), [rows])
  const avg3 = last3.length ? last3.reduce((a, r) => a + r.annual_turnover, 0) / last3.length : null
  const stale = rows && rows.length > 0 && latest && latest.fiscal_year < completedFy()

  async function save(values: Record<string, any>) {
    const body = values as Omit<FinancialYear, 'id'>
    if (editing?.id) await kbApi.updateFinancial(editing.id, body)
    else await kbApi.createFinancial(body)
    await load()
  }

  async function remove(r: FinancialYear) {
    if (!confirm(fyLabel(r.fiscal_year))) return
    await kbApi.deleteFinancial(r.id)
    await load()
  }

  if (!rows) return <Loading />

  const cards = [
    { label: `Turnover (${latest ? fyLabel(latest.fiscal_year) : 'latest'})`, value: inrShort(latest?.annual_turnover) },
    { label: 'Average turnover, last 3 years', value: inrShort(avg3) },
    { label: 'Net worth (latest)', value: inrShort(latest?.net_worth) },
    { label: 'Working capital (latest)', value: inrShort(latest?.working_capital) },
  ]

  return (
    <>
      <div className="kb-stats" style={{ marginTop: 0 }}>
        {cards.map(c => (
          <div key={c.label} className="kb-stat">
            <div className="min-w-0">
              <div className="kb-stat-value">{c.value}</div>
              <div className="kb-stat-label">{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      <Panel icon={<DollarSign size={18} />} title="Year-wise financial performance"
        sub="Audited figures in rupees. The tender check reads turnover, net worth, working capital and profit from here."
        action={<button className="kb-btn primary" onClick={() => setEditing({})}><Plus size={14} /> Add financial year</button>}>
        {stale && (
          <p className="kb-meta flex items-start gap-2" style={{ color: 'var(--warn)' }} role="status">
            <AlertTriangle size={15} className="shrink-0 mt-0.5" />
            The latest year on record is {fyLabel(latest!.fiscal_year)}. Tenders that ask for the last three years stay “check by hand” until the newer years are added.
          </p>
        )}
        {rows.length === 0 ? <div className="kb-empty">No financial years yet. Add the audited figures to let the tender check compare turnover and net worth.</div> : (
          <div className="kb-table-wrap">
            <table className="kb-table">
              <thead><tr>
                <th>Financial year</th><th className="num">Turnover</th><th className="num">Net profit</th><th className="num">Net worth</th>
                <th className="num">Working capital</th><th className="num">EBITDA</th><th>Auditor</th><th>Signed off</th><th />
              </tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    <td className="font-semibold">{fyLabel(r.fiscal_year)}</td>
                    <td className="num kb-money">{inrShort(r.annual_turnover)}</td>
                    <td className="num">{inrShort(r.net_profit)}</td>
                    <td className="num">{inrShort(r.net_worth)}</td>
                    <td className="num">{inrShort(r.working_capital)}</td>
                    <td className="num">{inrShort(r.ebitda)}</td>
                    <td>{r.audit_firm ?? '—'}</td>
                    <td>{dateText(r.audit_signoff_date)}</td>
                    <td>
                      <div className="flex gap-1 justify-end">
                        <button className="kb-icon-btn" onClick={() => setEditing(r)} aria-label={`Edit ${fyLabel(r.fiscal_year)}`}><Pencil size={14} /></button>
                        <button className="kb-icon-btn danger" onClick={() => remove(r)} aria-label={`Delete ${fyLabel(r.fiscal_year)}`}><Trash2 size={14} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <ProfileForm profile={profile} ids={['financial_strength']} layout="stack" icons={{ financial_strength: <Landmark size={18} /> }} />

      {editing && (
        <RecordModal<FinancialYear> title={editing.id ? `Edit ${fyLabel(editing.fiscal_year!)}` : 'Add financial year'} fields={FIELDS} initial={editing} wide
          onSave={save} onClose={() => setEditing(null)} />
      )}
    </>
  )
}
