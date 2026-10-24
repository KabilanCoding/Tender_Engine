import { Fragment, useEffect, useMemo, useState } from 'react'
import { Award, Briefcase, Building2, Eye, MapPin, Network, Paperclip, Pencil, Plus, Search, Server, Trash2, UserCheck, X } from 'lucide-react'
import { kbApi, type Certification, type Client, type Employee, type Office, type OemPartner, type Project, type Technology } from '../../../api/knowledgeBase'
import { Loading, Panel, RecordModal, dateText, inrFull, useConfirm, type FieldDef } from './ui'
import { ProjectDocsPanel } from './ProjectDocs'
import { AttachChip, KbDialog, KbFilesProvider } from './KbFiles'

function useRows<T>(load: () => Promise<{ data: T[] }>) {
  const [rows, setRows] = useState<T[] | null>(null)
  const reload = () => load().then(r => setRows(r.data))
  useEffect(() => { reload() }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return [rows, reload] as const
}

const AddButton = ({ label, onClick }: { label: string; onClick: () => void }) =>
  <button className="kb-btn primary" onClick={onClick}><Plus size={14} /> {label}</button>

const RowActions = ({ onEdit, onDelete, name, extra }: { onEdit: () => void; onDelete: () => void; name: string; extra?: React.ReactNode }) => (
  <div className="flex items-center gap-1">
    {extra}
    <button className="kb-icon-btn" onClick={onEdit} aria-label={`Edit ${name}`} title="Edit"><Pencil size={14} /></button>
    <button className="kb-icon-btn danger" onClick={onDelete} aria-label={`Delete ${name}`} title="Delete"><Trash2 size={14} /></button>
  </div>
)

// ── Technologies ──────────────────────────────────────────────────────────────

const TECH_FIELDS: FieldDef[] = [
  { key: 'name', label: 'Technology', required: true, hint: 'Platform with its stack in brackets, for example Android (Kotlin, Java)' },
  { key: 'category', label: 'Category', hint: 'For example Native Mobile, Backend Runtime, Relational Database, Cloud Platform' },
  { key: 'proficiency', label: 'Proficiency', type: 'select', options: ['Beginner', 'Intermediate', 'Advanced', 'Expert'] },
  { key: 'experience_years', label: 'Years of experience', type: 'number' },
  { key: 'canonical_id', label: 'Standard name (used for matching)', mono: true, hint: 'Optional. Leave empty unless the tender engine should treat it as another technology.' },
]

// Many small categories ("Native Mobile", "Backend Runtime" ...) are shown under a few families; the stored category is unchanged.
const FAMILIES: { name: string; rx: RegExp; accent: string }[] = [
  { name: 'Mobile', rx: /mobile|android|ios\b/i, accent: '#e07a1f' },
  { name: 'Frontend & Web', rx: /frontend|\bui\b|web programming/i, accent: '#2f6fde' },
  { name: 'Backend & APIs', rx: /backend|enterprise|api|runtime|web framework/i, accent: '#014BAA' },
  { name: 'Data & Storage', rx: /database|cache|queue|search|stream|analytics|data/i, accent: '#0f9b8e' },
  { name: 'Cloud & DevOps', rx: /cloud|container|devops|operating system|infra/i, accent: '#5b6b8a' },
  { name: 'AI & Documents', rx: /artificial|\bai\b|neural|llm|optical|ocr|pdf|document|machine/i, accent: '#4f9a2c' },
  { name: 'Security', rx: /secur|crypt/i, accent: '#d64545' },
  { name: 'IoT & Devices', rx: /iot|mqtt|embedded|device/i, accent: '#b8862c' },
  { name: 'Quality & Testing', rx: /test|qa\b|quality/i, accent: '#0f8a9d' },
]
const familyOf = (cat: string) => FAMILIES.find(f => f.rx.test(cat)) ?? { name: 'Other', rx: /./, accent: '#64748b' }
/** "Android (Kotlin)" -> platform "Android", stack ["Kotlin"] */
function splitStack(name: string): { platform: string; stack: string[] } {
  const m = name.match(/^(.*?)\s*\((.+)\)\s*$/)
  return m ? { platform: m[1], stack: m[2].split(/\s*[/,]\s*/).filter(Boolean) } : { platform: name, stack: [] }
}

export function TechnologiesPanel() {
  const [rows, reload] = useRows<Technology>(kbApi.listTechnologies)
  const [editing, setEditing] = useState<Partial<Technology> | null>(null)
  const confirm = useConfirm()
  const families = useMemo(() => {
    const m = new Map<string, { accent: string; cats: Map<string, Technology[]> }>()
    for (const t of rows ?? []) {
      const cat = t.category || 'Other', fam = familyOf(cat)
      if (!m.has(fam.name)) m.set(fam.name, { accent: fam.accent, cats: new Map() })
      const cats = m.get(fam.name)!.cats
      cats.set(cat, [...(cats.get(cat) ?? []), t])
    }
    const order = [...FAMILIES.map(f => f.name), 'Other']
    return [...m.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
  }, [rows])
  if (!rows) return <Loading />
  return (
    <Panel icon={<Server size={18} />} title={`Technical capabilities and services (${rows.length})`}
      sub="Grouped by area. Each platform shows its stack underneath. The tender check uses these for platform, language and tool requirements."
      action={<AddButton label="Add technology" onClick={() => setEditing({})} />}>
      {families.length === 0 ? <div className="kb-empty">No technologies yet.</div> : (
        <div className="kb-families">
          {families.map(([fam, { accent, cats }]) => (
            <section key={fam} className="kb-family" style={{ ['--fam' as string]: accent }}>
              <header className="kb-family-head"><span className="kb-family-dot" />{fam}<span className="kb-meta">{[...cats.values()].flat().length}</span></header>
              {[...cats.entries()].map(([cat, items]) => (
                <div key={cat} className="kb-family-cat">
                  <p className="kb-family-cat-name">{cat}</p>
                  <div className="kb-stack-list">
                    {items.map(t => {
                      const { platform, stack } = splitStack(t.name)
                      return (
                        <div key={t.id} className="kb-stack">
                          <div className="kb-stack-top">
                            <button type="button" className="kb-stack-name" onClick={() => setEditing(t)} title="Edit">{platform}</button>
                            {t.proficiency && <span className="kb-pill">{t.proficiency}</span>}
                            {t.experience_years ? <span className="kb-meta">{t.experience_years} yrs</span> : null}
                            <button type="button" className="kb-icon-btn danger ml-auto" aria-label={`Delete ${t.name}`}
                              onClick={async () => { if (confirm(t.name)) { await kbApi.deleteTechnology(t.id); reload() } }}><Trash2 size={13} /></button>
                          </div>
                          {stack.length > 0 && <div className="kb-stack-tags">{stack.map(x => <span key={x} className="kb-tag">{x}</span>)}</div>}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
      {editing && <RecordModal<Technology> title={editing.id ? 'Edit technology' : 'Add technology'} fields={TECH_FIELDS} initial={editing}
        onSave={async v => { editing.id ? await kbApi.updateTechnology(editing.id, v) : await kbApi.createTechnology(v as Omit<Technology, 'id'>); await reload() }}
        onClose={() => setEditing(null)} />}
    </Panel>
  )
}

// ── Certifications ────────────────────────────────────────────────────────────

const CERT_FIELDS: FieldDef[] = [
  { key: 'name', label: 'Certification', required: true, span2: true, placeholder: 'For example ISO 9001:2015' },
  { key: 'certificate_number', label: 'Certificate number', mono: true },
  { key: 'cert_code', label: 'Internal ID', mono: true, hint: 'Optional. Must be unique.' },
  { key: 'issuing_body', label: 'Issued by' },
  { key: 'status', label: 'Status', type: 'select', options: ['Active', 'In renewal', 'Expired', 'Suspended'] },
  { key: 'issued_on', label: 'Issued on', type: 'date' },
  { key: 'valid_until_date', label: 'Valid until', type: 'date' },
]

function certState(c: Certification): { label: string; tone: string } {
  const end = c.valid_until_date ?? (c.valid_until && /^\d{4}-\d{2}-\d{2}/.test(c.valid_until) ? c.valid_until : null)
  if (!end) return { label: c.valid_until ? `Valid to ${c.valid_until}` : 'No expiry recorded', tone: 'info' }
  const days = Math.floor((new Date(end).getTime() - Date.now()) / 86400000)
  if (days < 0) return { label: `Expired ${dateText(end)}`, tone: 'bad' }
  if (days <= 90) return { label: `Expires ${dateText(end)} (${days} days)`, tone: 'warn' }
  return { label: `Valid to ${dateText(end)}`, tone: 'ok' }
}

export function CertificationsPanel() {
  const [rows, reload] = useRows<Certification>(kbApi.listCertifications)
  const [editing, setEditing] = useState<Partial<Certification> | null>(null)
  const confirm = useConfirm()
  if (!rows) return <Loading />
  return (
    <Panel icon={<Award size={18} />} title={`Quality and domain certifications (${rows.length})`}
      sub="Attach each certificate's PDF. The tender check compares the certificate and its validity date with the tender's requirement."
      action={<AddButton label="Add certification" onClick={() => setEditing({})} />}>
      {rows.length === 0 ? <div className="kb-empty">No certifications yet.</div> : (
        <KbFilesProvider ownerType="certification">
          <div className="kb-table-wrap">
            <table className="kb-table">
              <thead><tr><th>Certification</th><th>Number</th><th>Issued by</th><th>Validity</th><th>Status</th><th>Certificate file</th><th /></tr></thead>
              <tbody>
                {rows.map(c => {
                  const st = certState(c)
                  return (
                    <tr key={c.id}>
                      <td className="font-semibold">{c.name}</td>
                      <td className="font-mono kb-meta">{c.certificate_number ?? '—'}</td>
                      <td>{c.issuing_body ?? '—'}</td>
                      <td><span className={`kb-pill ${st.tone}`}>{st.label}</span></td>
                      <td>{c.status ? <span className="kb-pill">{c.status}</span> : '—'}</td>
                      <td><AttachChip ownerKey={String(c.id)} label={c.name} /></td>
                      <td><RowActions name={c.name} onEdit={() => setEditing(c)} onDelete={async () => { if (confirm(c.name)) { await kbApi.deleteCertification(c.id); reload() } }} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </KbFilesProvider>
      )}
      {editing && <RecordModal<Certification> title={editing.id ? 'Edit certification' : 'Add certification'} fields={CERT_FIELDS} initial={editing}
        onSave={async v => {
          const body = { ...v, valid_until: v.valid_until_date ?? editing.valid_until ?? null }
          editing.id ? await kbApi.updateCertification(editing.id, body) : await kbApi.createCertification(body as Omit<Certification, 'id'>)
          await reload()
        }}
        onClose={() => setEditing(null)} />}
    </Panel>
  )
}

// ── Clients ───────────────────────────────────────────────────────────────────

const CLIENT_FIELDS: FieldDef[] = [
  { key: 'name', label: 'Client', required: true, span2: true },
  { key: 'client_code', label: 'Client ID', mono: true, hint: 'Optional. Must be unique.' },
  { key: 'client_type', label: 'Organisation type', hint: 'For example State Government Department, PSU, Private' },
  { key: 'industry', label: 'Industry / sector' },
  { key: 'state_region', label: 'State / region' },
  { key: 'country', label: 'Country' },
  { key: 'contact_email', label: 'Contact e-mail' },
  { key: 'engagement_status', label: 'Engagement', type: 'select', options: ['Active', 'Completed', 'Prospect', 'Dormant'] },
  { key: 'notes', label: 'Notes', type: 'textarea' },
]

export function ClientsPanel() {
  const [rows, reload] = useRows<Client>(kbApi.listClients)
  const [editing, setEditing] = useState<Partial<Client> | null>(null)
  const confirm = useConfirm()
  if (!rows) return <Loading />
  return (
    <Panel icon={<Building2 size={18} />} title={`Clients (${rows.length})`} sub="Who the work was done for. The client type decides whether a project counts as government experience."
      action={<AddButton label="Add client" onClick={() => setEditing({})} />}>
      {rows.length === 0 ? <div className="kb-empty">No clients yet.</div> : (
        <div className="kb-table-wrap">
          <table className="kb-table">
            <thead><tr><th>ID</th><th>Client</th><th>Type</th><th>Industry</th><th>State</th><th>Country</th><th>E-mail</th><th /></tr></thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id}>
                  <td className="font-mono kb-meta">{c.client_code ?? '—'}</td>
                  <td className="font-semibold">{c.name}</td>
                  <td>{c.client_type ?? '—'}</td>
                  <td>{c.industry ?? '—'}</td>
                  <td>{c.state_region ?? '—'}</td>
                  <td>{c.country ?? '—'}</td>
                  <td>{c.contact_email ?? '—'}</td>
                  <td><RowActions name={c.name} onEdit={() => setEditing(c)} onDelete={async () => { if (confirm(c.name)) { await kbApi.deleteClient(c.id); reload() } }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <RecordModal<Client> title={editing.id ? 'Edit client' : 'Add client'} fields={CLIENT_FIELDS} initial={editing} wide
        onSave={async v => { editing.id ? await kbApi.updateClient(editing.id, v) : await kbApi.createClient(v as Omit<Client, 'id'>); await reload() }}
        onClose={() => setEditing(null)} />}
    </Panel>
  )
}

// ── Projects ──────────────────────────────────────────────────────────────────

export const PORTFOLIO_CATEGORIES = ['GPS & Tracking', 'IoT & Telemetry', 'Ticketing & Fare Collection', 'Video & Surveillance',
  'GIS & Mapping', 'Hardware & Devices', 'Software & Platforms']
function yearSpan(p: Project): string {
  const a = p.start_date ? new Date(p.start_date).getFullYear() : null, b = p.completion_date ? new Date(p.completion_date).getFullYear() : null
  return a && b ? (a === b ? String(a) : `${a} – ${b}`) : String(a ?? b ?? '—')
}

export function ProjectsPanel({ onCount }: { onCount?: (n: number) => void }) {
  const [rows, reload] = useRows<Project>(kbApi.listProjects)
  const [clients] = useRows<Client>(kbApi.listClients)
  const [editing, setEditing] = useState<Partial<Project> | null>(null)
  const [viewing, setViewing] = useState<Project | null>(null)
  const [attachFor, setAttachFor] = useState<Project | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const confirm = useConfirm()
  useEffect(() => { if (rows) onCount?.(rows.length) }, [rows])   // eslint-disable-line react-hooks/exhaustive-deps

  const clientOf = (p: Project) => clients?.find(c => c.id === p.client_id)
  const fields: FieldDef[] = [
    { key: 'name', label: 'Assignment / project name', required: true, span2: true },
    { key: 'project_code', label: 'Project ID', mono: true, hint: 'Optional. Must be unique.' },
    { key: 'client_id', label: 'Client', type: 'select', options: (clients ?? []).map(c => ({ value: c.id, label: c.name })) },
    { key: 'order_no', label: 'Work order number', mono: true },
    { key: 'work_order_date', label: 'Work order date', type: 'date' },
    { key: 'total_value', label: 'Contract value (INR, excl. GST)', type: 'number', mono: true },
    { key: 'status', label: 'Status', type: 'select', options: ['completed', 'ongoing', 'on hold'] },
    { key: 'start_date', label: 'Start date', type: 'date' },
    { key: 'completion_date', label: 'Completion date', type: 'date' },
    { key: 'portfolio_category', label: 'Portfolio category', type: 'select', options: PORTFOLIO_CATEGORIES,
      hint: 'Where the project is filed in the portfolio. Left empty, it is chosen from the project name.' },
    { key: 'domain', label: 'Domain / sector' },
    { key: 'project_role', label: 'Our role', type: 'select', options: ['Main contractor', 'Sub-contractor', 'Consortium member'] },
    { key: 'team_size', label: 'Team size', type: 'number' },
    { key: 'duration_weeks', label: 'Duration (weeks)', type: 'number' },
    { key: 'technologies', label: 'Technologies / scope', type: 'list', span2: true, hint: 'Separate with commas' },
    { key: 'evidence_files', label: 'Evidence documents', type: 'list', span2: true, hint: 'Names of the work order and completion certificate files, separated by commas' },
    { key: 'description', label: 'Scope summary', type: 'textarea' },
  ]

  const groups = useMemo(() => {
    const m = new Map<string, Project[]>()
    for (const p of rows ?? []) { const s = p.portfolio_category || 'Uncategorised'; m.set(s, [...(m.get(s) ?? []), p]) }
    const order = [...PORTFOLIO_CATEGORIES, 'Uncategorised']
    return [...m.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))
  }, [rows])

  if (!rows) return <Loading />
  return (
    <Panel icon={<Briefcase size={18} />} title={`Executed and ongoing work orders (${rows.length})`}
      sub="Grouped by portfolio category. The tender check matches these against “similar work” requirements. Open a row's documents to attach the work order and completion certificate."
      action={<AddButton label="Add work order" onClick={() => setEditing({ status: 'completed', project_role: 'Main contractor' })} />}>
      {rows.length === 0 ? <div className="kb-empty">No work orders yet.</div> : (
        <div className="flex flex-col gap-5">
          {groups.map(([sector, items]) => (
            <section key={sector}>
              <header className="kb-sector-head">
                <span>{sector}</span>
                <span className="kb-meta">{items.length} project{items.length === 1 ? '' : 's'} · {inrFull(items.reduce((t, p) => t + (p.total_value || 0), 0))}</span>
              </header>
              <div className="kb-table-wrap">
                <table className="kb-table kb-proj-table">
                  <thead><tr><th>ID</th><th>Project</th><th>Client</th><th className="text-right">Value (excl. GST)</th><th>Period</th><th>Status</th><th>Documents</th><th /></tr></thead>
                  <tbody>
                    {items.map(p => {
                      const cl = clientOf(p)
                      const isOpen = open === p.id
                      return (
                        <Fragment key={p.id}>
                          <tr className={isOpen ? 'is-open' : ''}>
                            <td><span className="kb-code">{p.project_code ?? '—'}</span></td>
                            <td><button type="button" className="kb-link" onClick={() => setViewing(p)}>{p.name}</button>
                              <div className="kb-meta">{p.domain ?? ''}</div></td>
                            <td><div>{cl?.name ?? '—'}</div><div className="kb-meta">{cl?.client_type ?? ''}</div></td>
                            <td className="text-right kb-money">{inrFull(p.total_value)}</td>
                            <td className="whitespace-nowrap">{yearSpan(p)}</td>
                            <td><span className={`kb-pill ${p.status === 'completed' ? 'ok' : p.status === 'ongoing' ? 'info' : 'warn'}`}>{p.status}</span></td>
                            <td><button type="button" className={`kb-attach ${isOpen ? 'has' : ''}`} onClick={() => setOpen(isOpen ? null : p.id)} aria-expanded={isOpen}>
                              <Paperclip size={12} /> {isOpen ? 'Hide' : 'Documents'}</button></td>
                            <td><RowActions name={p.name} onEdit={() => setEditing(p)} onDelete={async () => { if (confirm(p.name)) { await kbApi.deleteProject(p.id); reload() } }}
                              extra={<button className="kb-icon-btn" onClick={() => setViewing(p)} aria-label={`View ${p.name}`} title="View"><Eye size={14} /></button>} /></td>
                          </tr>
                          {isOpen && <tr className="kb-docs-row"><td colSpan={8}><ProjectDocsPanel projectId={p.id} /></td></tr>}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}

      {editing && <RecordModal<Project> title={editing.id ? 'Edit work order' : 'Add work order · step 1 of 2'} fields={fields} initial={editing} wide
        onSave={async v => {
          const body = { ...v, client_id: v.client_id ? Number(v.client_id) : null, status: v.status ?? 'completed' }
          if (editing.id) await kbApi.updateProject(editing.id, body)
          else { const { data } = await kbApi.createProject(body as Omit<Project, 'id'>); setAttachFor(data) }   // next step: its documents
          await reload()
        }}
        onClose={() => setEditing(null)} />}

      {attachFor && (
        <KbDialog wide label="Step 2 of 2 · Attach documents" title={attachFor.name} onClose={() => setAttachFor(null)}>
          <p className="kb-meta">The work order is saved under <b>{attachFor.portfolio_category ?? 'its category'}</b>. Attach its work order,
            completion certificate and other files now, or later from the row's Documents button.</p>
          <ProjectDocsPanel projectId={attachFor.id} />
          <div className="flex justify-end"><button className="kb-btn primary" onClick={() => setAttachFor(null)}>Done</button></div>
        </KbDialog>
      )}

      {viewing && (
        <KbDialog wide label={[viewing.project_code, viewing.status, viewing.project_role].filter(Boolean).join(' · ')} title={viewing.name} onClose={() => setViewing(null)}>
            <div className="kb-fields">
              {[
                ['Client', clientOf(viewing)?.name], ['Client type', clientOf(viewing)?.client_type],
                ['Work order', [viewing.order_no, viewing.work_order_date && dateText(viewing.work_order_date)].filter(Boolean).join(' · ')],
                ['Contract value (excl. GST)', inrFull(viewing.total_value)],
                ['Period', `${dateText(viewing.start_date)} to ${dateText(viewing.completion_date)}`],
                ['Domain', viewing.domain], ['Team size', viewing.team_size], ['Duration', viewing.duration_weeks ? `${viewing.duration_weeks} weeks` : null],
              ].map(([k, v]) => (
                <div key={String(k)} className="kb-card"><span className="kb-meta">{k}</span><b className="text-sm" style={{ color: 'var(--ink)' }}>{v || '—'}</b></div>
              ))}
            </div>
            {!!viewing.technologies?.length && <div><span className="kb-label">Technologies / scope</span><div className="flex flex-wrap gap-2">{viewing.technologies.map(t => <span key={t} className="kb-tag">{t}</span>)}</div></div>}
            <div className="kb-card"><span className="kb-label">Scope summary</span><p className="kb-meta" style={{ whiteSpace: 'pre-wrap' }}>{viewing.description || 'No scope summary recorded.'}</p></div>
            {!!viewing.evidence_files?.length && <div><span className="kb-label">Evidence documents named in the record</span><div className="flex flex-wrap gap-2">{viewing.evidence_files.map(f => <span key={f} className="kb-pill info">{f}</span>)}</div></div>}
            <div><span className="kb-label">Uploaded documents</span><ProjectDocsPanel projectId={viewing.id} /></div>
        </KbDialog>
      )}
    </Panel>
  )
}

// ── Workforce ─────────────────────────────────────────────────────────────────

const EMP_FIELDS: FieldDef[] = [
  { key: 'name', label: 'Full name', required: true },
  { key: 'role', label: 'Designation', required: true },
  { key: 'employee_code', label: 'Employee ID', mono: true, hint: 'Optional. Must be unique.' },
  { key: 'department', label: 'Department' },
  { key: 'level', label: 'Level', type: 'select', options: ['Junior', 'Mid', 'Senior', 'Executive'] },
  { key: 'work_mode', label: 'Deployment / mode', type: 'select', options: ['Onsite - HQ', 'Onsite - Client Site', 'Hybrid'] },
  { key: 'experience_years', label: 'Total experience (years)', type: 'number' },
  { key: 'relevant_experience_years', label: 'Relevant experience (years)', type: 'number' },
  { key: 'govt_experience_years', label: 'Government project experience (years)', type: 'number' },
  { key: 'joining_date', label: 'Joining date', type: 'date' },
  { key: 'hourly_rate', label: 'Hourly rate (INR)', type: 'number', hint: 'Used by the cost estimate only' },
  { key: 'qualification', label: 'Qualification', span2: true },
  { key: 'professional_certifications', label: 'Professional certifications', span2: true },
  { key: 'skills', label: 'Skills / primary tech stack', type: 'list', span2: true, hint: 'Separate with commas' },
  { key: 'is_key_personnel', label: 'Key personnel (named in tender proposals)', type: 'bool' },
  { key: 'is_active', label: 'Active employee', type: 'bool' },
]

export function WorkforcePanel({ onCount }: { onCount?: (n: number) => void }) {
  const [rows, reload] = useRows<Employee>(kbApi.listEmployees)
  const [editing, setEditing] = useState<Partial<Employee> | null>(null)
  const [q, setQ] = useState('')
  const confirm = useConfirm()
  useEffect(() => { if (rows) onCount?.(rows.filter(r => r.is_active).length) }, [rows])   // eslint-disable-line react-hooks/exhaustive-deps

  const active = (rows ?? []).filter(r => r.is_active)
  const key = active.filter(r => r.is_key_personnel)
  const avg = active.length ? active.reduce((a, r) => a + (r.experience_years ?? 0), 0) / active.length : 0
  const modes = useMemo(() => {
    const m: Record<string, number> = {}
    for (const r of active) m[r.work_mode || 'Not set'] = (m[r.work_mode || 'Not set'] ?? 0) + 1
    return Object.entries(m)
  }, [rows])   // eslint-disable-line react-hooks/exhaustive-deps
  const shown = (rows ?? []).filter(r => {
    const t = q.trim().toLowerCase()
    return !t || [r.name, r.role, r.department, r.employee_code, r.work_mode, ...(r.skills ?? [])].some(x => String(x ?? '').toLowerCase().includes(t))
  })

  if (!rows) return <Loading />
  const summary = [
    { label: 'Active employees', value: active.length },
    { label: 'Key personnel on proposals', value: key.length },
    { label: 'Average experience', value: `${avg.toFixed(1)} yrs` },
    { label: 'Deployment', value: modes.map(([k, v]) => `${v} ${k.replace('Onsite - ', '')}`).join(' · ') || '—' },
  ]
  return (
    <>
      <div className="kb-stats" style={{ marginTop: 0 }}>
        {summary.map(s => (
          <div key={s.label} className="kb-stat"><div className="min-w-0"><div className="kb-stat-value" style={s.label === 'Deployment' ? { fontSize: '0.8rem', fontFamily: 'var(--font-ui)', letterSpacing: 0, lineHeight: 1.35 } : undefined}>{s.value}</div><div className="kb-stat-label">{s.label}</div></div></div>
        ))}
      </div>

      <Panel icon={<UserCheck size={18} />} title={`Key personnel (${key.length})`} sub="Proposal candidates: senior people the tender's “key team” requirements are checked against.">
        {key.length === 0 ? <div className="kb-empty">No one is marked as key personnel. Open an employee and switch on “Key personnel”.</div> : (
          <div className="kb-cards">
            {key.map(p => (
              <div key={p.id} className="kb-card">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="kb-card-title">{p.name}</div><div className="text-xs font-semibold" style={{ color: 'var(--kb-accent-text, var(--brand-blue-dark))' }}>{p.role}</div></div>
                  {p.employee_code && <span className="kb-code">{p.employee_code}</span>}
                </div>
                <p className="kb-meta">Total <b>{p.experience_years ?? '—'} yrs</b> · Relevant <b>{p.relevant_experience_years ?? '—'} yrs</b> · Govt <b>{p.govt_experience_years ?? '—'} yrs</b></p>
                <p className="kb-meta">Qualification: <b>{p.qualification ?? '—'}</b></p>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel icon={<UserCheck size={18} />} title={`Employee roster (${rows.length})`} sub="Everyone the company can put on a project."
        action={<AddButton label="Add employee" onClick={() => setEditing({ is_active: true, level: 'Mid' })} />}>
        <div className="relative max-w-md">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--ink-3)' }} />
          <input className="kb-input" style={{ paddingLeft: '2.2rem' }} placeholder="Filter by name, designation, skill, mode…" value={q} onChange={e => setQ(e.target.value)} aria-label="Filter employees" />
        </div>
        <div className="kb-table-wrap">
          <table className="kb-table">
            <thead><tr><th>ID</th><th>Name</th><th>Designation</th><th>Department</th><th className="num">Exp.</th><th>Skills</th><th>Mode</th><th /></tr></thead>
            <tbody>
              {shown.map(e => (
                <tr key={e.id} style={e.is_active ? undefined : { opacity: 0.55 }}>
                  <td className="font-mono kb-meta">{e.employee_code ?? '—'}</td>
                  <td className="font-semibold">{e.name} {e.is_key_personnel && <span className="kb-pill info">Key</span>}</td>
                  <td>{e.role}</td>
                  <td>{e.department ?? '—'}</td>
                  <td className="num">{e.experience_years ?? '—'}</td>
                  <td className="kb-meta" style={{ maxWidth: '16rem' }}>{(e.skills ?? []).slice(0, 4).join(', ') || '—'}</td>
                  <td>{e.work_mode ? <span className={`kb-pill ${e.work_mode.includes('Client') ? 'warn' : e.work_mode === 'Hybrid' ? 'info' : ''}`}>{e.work_mode}</span> : '—'}</td>
                  <td><RowActions name={e.name} onEdit={() => setEditing(e)} onDelete={async () => { if (confirm(e.name)) { await kbApi.deleteEmployee(e.id); reload() } }} /></td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td colSpan={8} className="text-center kb-meta" style={{ padding: '1.5rem' }}>No employee matches.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      {editing && <RecordModal<Employee> title={editing.id ? 'Edit employee' : 'Add employee'} fields={EMP_FIELDS} initial={editing} wide
        onSave={async v => { editing.id ? await kbApi.updateEmployee(editing.id, v) : await kbApi.createEmployee(v as Omit<Employee, 'id'>); await reload() }}
        onClose={() => setEditing(null)} />}
    </>
  )
}

// ── Partners and offices ──────────────────────────────────────────────────────

const OEM_FIELDS: FieldDef[] = [
  { key: 'oem', label: 'Product maker (OEM)', required: true },
  { key: 'product', label: 'Product / platform' },
  { key: 'partner_type', label: 'Partnership type', type: 'select', options: ['Authorised partner', 'Reseller', 'Consulting partner', 'Cloud solution provider', 'System integrator', 'Distributor'] },
  { key: 'status', label: 'Status', type: 'select', options: ['Active', 'Expired', 'Inactive'] },
  { key: 'since_year', label: 'Partner since (year)', type: 'number' },
  { key: 'territory', label: 'Territory' },
  { key: 'authorization_ref', label: 'Authorisation letter reference', span2: true, mono: true },
]
const OFFICE_FIELDS: FieldDef[] = [
  { key: 'city', label: 'City', required: true },
  { key: 'state', label: 'State' },
  { key: 'office_type', label: 'Office type', type: 'select', options: ['Registered office', 'Corporate office', 'Branch office', 'Delivery centre', 'Project site office'] },
  { key: 'tenure', label: 'Owned or rented', type: 'select', options: ['Owned', 'Rented'] },
  { key: 'employee_capacity', label: 'People it can seat', type: 'number' },
  { key: 'address', label: 'Address', type: 'textarea' },
]

export function PartnersPanel() {
  const [oem, reloadOem] = useRows<OemPartner>(kbApi.listOem)
  const [offices, reloadOff] = useRows<Office>(kbApi.listOffices)
  const [editOem, setEditOem] = useState<Partial<OemPartner> | null>(null)
  const [editOff, setEditOff] = useState<Partial<Office> | null>(null)
  const confirm = useConfirm()
  if (!oem || !offices) return <Loading />
  return (
    <div className="kb-grid cols-2">
      <Panel icon={<Network size={18} />} title={`OEM partnerships (${oem.length})`} sub="Tenders often ask for an authorisation letter from the product maker."
        action={<AddButton label="Add partnership" onClick={() => setEditOem({ status: 'Active' })} />}>
        {oem.length === 0 ? <div className="kb-empty">No OEM partnerships recorded.</div> : (
          <div className="flex flex-col gap-3">
            {oem.map(m => (
              <div key={m.id} className="kb-card">
                <div className="flex items-start justify-between gap-2">
                  <span className="kb-card-title">{m.oem}</span>
                  <RowActions name={m.oem} onEdit={() => setEditOem(m)} onDelete={async () => { if (confirm(m.oem)) { await kbApi.deleteOem(m.id); reloadOem() } }} />
                </div>
                <p className="kb-meta">{m.product ?? '—'} · <b>{m.partner_type ?? '—'}</b>{m.since_year ? ` since ${m.since_year}` : ''}{m.territory ? ` · ${m.territory}` : ''}</p>
                <div className="flex items-center gap-2 flex-wrap">
                  {m.status && <span className={`kb-pill ${m.status === 'Active' ? 'ok' : 'warn'}`}>{m.status}</span>}
                  {m.authorization_ref && <span className="kb-meta font-mono">{m.authorization_ref}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel icon={<MapPin size={18} />} title={`Offices (${offices.length})`} sub="Used when a tender asks for a local office in a state or city."
        action={<AddButton label="Add office" onClick={() => setEditOff({})} />}>
        {offices.length === 0 ? <div className="kb-empty">No offices recorded. Only the registered address is known.</div> : (
          <div className="flex flex-col gap-3">
            {offices.map(o => (
              <div key={o.id} className="kb-card">
                <div className="flex items-start justify-between gap-2">
                  <span className="kb-card-title">{o.city}{o.state ? `, ${o.state}` : ''}</span>
                  <RowActions name={o.city} onEdit={() => setEditOff(o)} onDelete={async () => { if (confirm(o.city)) { await kbApi.deleteOffice(o.id); reloadOff() } }} />
                </div>
                <p className="kb-meta"><b>{o.office_type ?? 'Office'}</b>{o.tenure ? ` · ${o.tenure}` : ''}{o.employee_capacity ? ` · seats ${o.employee_capacity}` : ''}</p>
                {o.address && <p className="kb-meta">{o.address}</p>}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {editOem && <RecordModal<OemPartner> title={editOem.id ? 'Edit partnership' : 'Add partnership'} fields={OEM_FIELDS} initial={editOem}
        onSave={async v => { editOem.id ? await kbApi.updateOem(editOem.id, v as Omit<OemPartner, 'id'>) : await kbApi.createOem(v as Omit<OemPartner, 'id'>); await reloadOem() }}
        onClose={() => setEditOem(null)} />}
      {editOff && <RecordModal<Office> title={editOff.id ? 'Edit office' : 'Add office'} fields={OFFICE_FIELDS} initial={editOff}
        onSave={async v => { editOff.id ? await kbApi.updateOffice(editOff.id, v as Omit<Office, 'id'>) : await kbApi.createOffice(v as Omit<Office, 'id'>); await reloadOff() }}
        onClose={() => setEditOff(null)} />}
    </div>
  )
}
