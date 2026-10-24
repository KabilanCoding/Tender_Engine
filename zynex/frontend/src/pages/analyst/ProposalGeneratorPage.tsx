import { useState, useEffect } from 'react'
import { FileText, Download, Loader, ChevronDown, ChevronUp, Briefcase, Building2, Users, ListChecks, CalendarRange, Wrench, IndianRupee } from 'lucide-react'
import { documentsApi, type Document } from '../../api/documents'
import { proposalsApi, type Proposal } from '../../api/proposals'
import { Article, PenNib } from '@phosphor-icons/react'

const SECTION_ICONS: Record<string, typeof FileText> = {
  executive_summary: Article, technical_approach: Wrench, project_plan: CalendarRange, team_composition: Users,
  company_profile: Building2, commercial_proposal: IndianRupee, compliance: ListChecks,
}

const SECTION_LABELS: Record<string, string> = {
  executive_summary: 'Executive Summary',
  technical_approach: 'Technical Approach',
  project_plan: 'Project Plan',
  team_composition: 'Team Composition',
  company_profile: 'Company Profile',
  commercial_proposal: 'Commercial Proposal',
  compliance: 'Compliance & Certifications',
}

export default function ProposalGeneratorPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>('executive_summary')

  useEffect(() => {
    documentsApi.list().then(r => {
      const analyzed = r.data.filter(d => d.status === 'ANALYZED')
      setDocuments(analyzed)
      if (analyzed.length > 0) setSelectedDocId(analyzed[0].id)
    })
  }, [])

  // which documents already have a proposal: asked once, so a document without one is not requested (no 404s)
  const [withProposal, setWithProposal] = useState<Set<number> | null>(null)
  useEffect(() => {
    proposalsApi.existing().then(r => setWithProposal(new Set(r.data))).catch(() => setWithProposal(new Set()))
  }, [])

  useEffect(() => {
    if (!selectedDocId || withProposal === null) return
    setProposal(null)
    if (!withProposal.has(selectedDocId)) return
    proposalsApi.get(selectedDocId)
      .then(r => setProposal(r.data))
      .catch(() => {})
  }, [selectedDocId, withProposal])

  async function generate() {
    if (!selectedDocId) return
    setGenerating(true)
    setError(null)
    try {
      const { data } = await proposalsApi.generate(selectedDocId)
      setProposal(data)
      setWithProposal(prev => new Set([...(prev ?? []), selectedDocId]))
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const sections = proposal?.sections ?? {}

  const ready = Object.keys(SECTION_LABELS).filter(k => sections[k]).length
  const selectedName = documents.find(d => d.id === selectedDocId)?.original_filename

  return (
    <div className="flex flex-col gap-6 max-w-[1100px]">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Bid documents</span>
          <h1 className="mt-1">Proposal Generator</h1>
          <p>Builds the technical and commercial proposal for an analysed tender from your company data. Download it as DOCX or PDF.</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-300 text-red-700 px-4 py-3 rounded-xl text-sm">{error}</div>
      )}

      {/* Controls */}
      <div className="bg-white rounded-2xl p-5 border flex flex-col sm:flex-row sm:items-end gap-4">
        <div className="flex-1 min-w-0">
          <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Analysed tender</label>
          <div className="relative">
            <FileText size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <select
              className="w-full appearance-none border border-gray-200 rounded-xl pl-9 pr-9 py-2.5 text-sm bg-white text-gray-800 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition"
              value={selectedDocId ?? ''}
              onChange={e => setSelectedDocId(Number(e.target.value))}
            >
              {documents.length === 0 && <option value="">No analysed documents found</option>}
              {documents.map(d => (
                <option key={d.id} value={d.id}>{d.original_filename}</option>
              ))}
            </select>
            <ChevronDown size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          </div>
        </div>
        <button
          onClick={generate}
          disabled={!selectedDocId || generating}
          className="zx-action primary justify-center disabled:opacity-50 disabled:pointer-events-none"
          style={{ padding: '0.7rem 1.25rem' }}
        >
          {generating ? <><Loader size={15} className="animate-spin" /> Generating…</> : <><PenNib size={16} /> {proposal ? 'Generate again' : 'Generate proposal'}</>}
        </button>
      </div>

      {generating && (
        <div className="bg-white rounded-2xl border p-5 flex flex-col gap-3" aria-live="polite">
          <p className="text-sm text-gray-600">Writing the proposal for <b className="text-gray-800">{selectedName}</b>. This runs on the local model and can take a few minutes.</p>
          {[78, 64, 90, 55].map((w, i) => <div key={i} className="zx-skel h-3 rounded" style={{ width: `${w}%` }} />)}
        </div>
      )}

      {proposal && (
        <>
          {/* Download bar */}
          <div className="bg-white rounded-2xl border p-4 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-3 mr-auto min-w-0">
              <div className="zx-stat-icon" style={{ width: '2.5rem', height: '2.5rem', borderRadius: '0.8rem' }}><Briefcase size={18} /></div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-800 truncate">{selectedName}</p>
                <p className="text-xs text-gray-500">{ready} of {Object.keys(SECTION_LABELS).length} sections written</p>
              </div>
            </div>
            <button
              onClick={() => selectedDocId && proposalsApi.downloadDocx(selectedDocId)}
              disabled={!proposal.docx_path}
              className="zx-action primary disabled:opacity-40 disabled:pointer-events-none"
            >
              <Download size={15} /> DOCX
            </button>
            <button
              onClick={() => selectedDocId && proposalsApi.downloadPdf(selectedDocId)}
              disabled={!proposal.pdf_path}
              className="zx-action disabled:opacity-40 disabled:pointer-events-none"
            >
              <Download size={15} /> PDF
            </button>
            {(!proposal.docx_path || !proposal.pdf_path) && (
              <span className="flex items-center gap-1.5 text-xs text-gray-500 w-full sm:w-auto">
                <Loader size={12} className="animate-spin" /> Files are being prepared…
              </span>
            )}
          </div>

          {/* Section accordion */}
          <div className="flex flex-col gap-2.5 zx-stagger">
            {Object.entries(SECTION_LABELS).map(([key, label], i) => {
              const content = sections[key]
              if (!content) return null
              const isOpen = expanded === key
              const Icon = SECTION_ICONS[key] ?? FileText
              return (
                <div key={key} className={`bg-white rounded-2xl border overflow-hidden transition-shadow ${isOpen ? 'shadow-md' : ''}`}>
                  <button
                    className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-gray-50 transition-colors"
                    onClick={() => setExpanded(isOpen ? null : key)}
                    aria-expanded={isOpen}
                  >
                    <span className="font-mono text-[11px] text-gray-400 w-5">{String(i + 1).padStart(2, '0')}</span>
                    <span className={`w-8 h-8 rounded-lg grid place-items-center ${isOpen ? 'bg-[#014BAA] text-white' : 'bg-gray-100 text-gray-500'} transition-colors`}><Icon size={15} /></span>
                    <span className="font-semibold text-gray-800 flex-1">{label}</span>
                    <span className="text-xs text-gray-400 hidden sm:inline">{content.split(/\s+/).length} words</span>
                    {isOpen ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-5 border-t border-gray-100">
                      <div className="mt-4 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed max-w-[75ch]">
                        {content}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}

      {!proposal && !generating && selectedDocId && (
        <div className="zx-empty">
          <div className="zx-empty-icon"><FileText size={28} strokeWidth={1.5} /></div>
          <h2>No proposal for this tender yet</h2>
          <p>Press "Generate proposal" to write these sections from the tender and your company data.</p>
          <div className="flex flex-wrap justify-center gap-2 mt-2 max-w-xl">
            {Object.entries(SECTION_LABELS).map(([key, label]) => {
              const Icon = SECTION_ICONS[key] ?? FileText
              return <span key={key} className="zx-chip inline-flex items-center gap-1.5"><Icon size={12} /> {label}</span>
            })}
          </div>
        </div>
      )}

      {!selectedDocId && documents.length === 0 && (
        <div className="zx-empty">
          <div className="zx-empty-icon"><FileText size={28} strokeWidth={1.5} /></div>
          <h2>Analyse a tender first</h2>
          <p>A proposal is written for a tender that has been analysed. Upload one under Tender Analysis.</p>
        </div>
      )}
    </div>
  )
}
