import { KbFilesProvider } from './kb/KbFiles'
import { useEffect, useState } from 'react'
import { Award, Briefcase, Building2, Check, DollarSign, Loader2, Network, Server, ShieldCheck, Users } from 'lucide-react'
import { kbApi, type IndexStatus } from '../../api/knowledgeBase'
import { ProfileForm, useProfile } from './kb/ProfileForm'
import FinancialsPanel from './kb/Financials'
import { CertificationsPanel, ClientsPanel, PartnersPanel, ProjectsPanel, TechnologiesPanel, WorkforcePanel } from './kb/Records'
import { inrShort } from './kb/ui'
import './kb/kb.css'

type Tab = 'identity' | 'financials' | 'tech' | 'certs' | 'projects' | 'workforce' | 'clients' | 'partners' | 'legal'

function SearchIndexCard() {
  const [status, setStatus] = useState<IndexStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = () => kbApi.indexStatus().then(r => setStatus(r.data)).catch(() => setStatus(null))
  useEffect(() => { load() }, [])
  const refresh = async () => {
    setBusy(true); setError('')
    try { await kbApi.rebuildIndex(); await load() }
    catch { setError('Could not refresh. Check that the embedding model is available on the Ollama server.') }
    finally { setBusy(false) }
  }
  // only shown when something needs attention (rows to refresh, or a refresh that just failed)
  if (!status || (status.ready && !error)) return null
  return (
    <div className="kb-panel" style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', padding: '0.9rem 1.25rem' }}>
      <div className="kb-meta" style={{ fontSize: '0.8rem' }}>
        <span className="font-semibold" style={{ color: 'var(--ink)' }}>Search index</span>{' '}
        {status.ready
          ? `is up to date (${status.indexed} of ${status.rows_in_tables} rows). Tender experience is also matched by meaning.`
          : `has ${status.out_of_date} row(s) to refresh before experience can be matched by meaning.`}
        {error && <span className="block kb-err mt-1" role="alert">{error}</span>}
      </div>
      <button onClick={refresh} disabled={busy}
        className="kb-btn primary">
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Refresh search index
      </button>
    </div>
  )
}


interface Counts { projects: number; certs: number; people: number; clients: number; netWorth: number | null }

export default function KnowledgeBasePage() {
  const [tab, setTab] = useState<Tab>('identity')
  const [logoOk, setLogoOk] = useState(true)
  const [counts, setCounts] = useState<Counts>({ projects: 0, certs: 0, people: 0, clients: 0, netWorth: null })
  const profile = useProfile()

  // the numbers in the hero and tab labels follow edits made in any tab
  useEffect(() => {
    Promise.all([kbApi.listProjects(), kbApi.listCertifications(), kbApi.listEmployees(), kbApi.listClients(), kbApi.listFinancials()])
      .then(([p, c, e, cl, f]) => setCounts({
        projects: p.data.length, certs: c.data.length, people: e.data.filter(x => x.is_active).length, clients: cl.data.length,
        netWorth: f.data.find(x => x.net_worth != null)?.net_worth ?? null,
      }))
      .catch(() => { /* the panels show their own load errors */ })
  }, [tab])

  const name = profile.value('company_legal_name') || 'Company knowledge base'
  const initials = name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase()
  const incorporated = profile.value('date_of_incorporation')
  const est = incorporated.match(/\d{4}/)?.[0]
  const hq = profile.value('registered_address').split(',').slice(-2).join(',').trim()

  const stats = [
    { label: 'Work orders', value: counts.projects, icon: Briefcase, color: '#014BAA' },
    { label: 'Certifications', value: counts.certs, icon: Award, color: '#d97706' },
    { label: 'Team size', value: counts.people, icon: Users, color: '#0891b2' },
    { label: 'Net worth', value: inrShort(counts.netWorth), icon: DollarSign, color: '#059669' },
  ]
  const tabs: { id: Tab; label: string; icon: typeof Building2; n?: number }[] = [
    { id: 'identity', label: 'Identity & registration', icon: Building2 },
    { id: 'financials', label: 'Financial performance', icon: DollarSign },
    { id: 'tech', label: 'Technical capabilities', icon: Server },
    { id: 'certs', label: 'Certifications', icon: Award, n: counts.certs },
    { id: 'projects', label: 'Projects portfolio', icon: Briefcase, n: counts.projects },
    { id: 'workforce', label: 'Workforce & roster', icon: Users, n: counts.people },
    { id: 'clients', label: 'Clients', icon: Building2, n: counts.clients },
    { id: 'partners', label: 'Partners & offices', icon: Network },
    { id: 'legal', label: 'Legal & compliance', icon: ShieldCheck },
  ]

  return (
    <div className="kb-master">
      <section className="kb-hero">
        <div className="kb-hero-glow" aria-hidden="true" />
        <div className="relative flex items-center gap-5 min-w-0">
          {logoOk ? (
            <div className="kb-logo-plate">
              <img src="/xenovex-mark.png" alt="Xenovex Technologies logo" className="kb-logo-img" onError={() => setLogoOk(false)} />
            </div>
          ) : (
            <div className="kb-avatar" aria-hidden="true">{initials || 'KB'}</div>
          )}
          <div className="min-w-0 flex flex-col gap-2">
            <span className="kb-eyebrow">Company knowledge base</span>
            <h1 className="kb-title">{name}</h1>
            <div className="flex items-center gap-2 flex-wrap">
              {profile.value('cin') && <span className="kb-chip"><span className="kb-chip-k">CIN</span><span className="font-mono">{profile.value('cin')}</span></span>}
              {est && <span className="kb-chip"><span className="kb-chip-k">Est.</span>{est}</span>}
              {hq && <span className="kb-chip"><span className="kb-chip-k">HQ</span>{hq}</span>}
            </div>
          </div>
        </div>
        <div className="kb-stats">
          {stats.map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="kb-stat">
              <span className="kb-stat-icon" style={{ background: `${color}22`, color }}><Icon size={17} /></span>
              <div className="min-w-0"><div className="kb-stat-value">{value}</div><div className="kb-stat-label">{label}</div></div>
            </div>
          ))}
        </div>
      </section>

      <SearchIndexCard />

      <nav className="kb-tabs" role="tablist" aria-label="Company knowledge base sections">
        {tabs.map(t => {
          const Icon = t.icon
          return (
            <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={`kb-tab ${tab === t.id ? 'is-active' : ''}`}>
              <Icon size={15} className="shrink-0" />
              <span>{t.label}</span>
              {t.n !== undefined && <span className="kb-tab-count">({t.n})</span>}
            </button>
          )
        })}
      </nav>

      <KbFilesProvider ownerType="profile">
      <div key={tab} className="kb-tabpanel" role="tabpanel">
        {tab === 'identity' && <ProfileForm profile={profile} ids={['identity', 'registrations', 'msme', 'standards']}
          icons={{ identity: <Building2 size={18} />, registrations: <ShieldCheck size={18} /> }} />}
        {tab === 'financials' && <FinancialsPanel profile={profile} />}
        {tab === 'tech' && <TechnologiesPanel />}
        {tab === 'certs' && <CertificationsPanel />}
        {tab === 'projects' && <ProjectsPanel />}
        {tab === 'workforce' && <WorkforcePanel />}
        {tab === 'clients' && <ClientsPanel />}
        {tab === 'partners' && <PartnersPanel />}
        {tab === 'legal' && <ProfileForm profile={profile} ids={['legal', 'bidding']} icons={{ legal: <ShieldCheck size={18} />, bidding: <Network size={18} /> }} />}
      </div>
      </KbFilesProvider>
    </div>
  )
}
