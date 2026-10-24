import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Eye, FileText, FolderOpen, Loader2, ScanText, Trash2, Upload } from 'lucide-react'
import { kbApi, type ProjectDocument } from '../../../api/knowledgeBase'
import { apiError } from './ui'
import { sizeText } from './KbFiles'

const CATEGORIES: { id: string; label: string }[] = [
  { id: 'SRS', label: 'SRS (requirements)' }, { id: 'TECHNICAL_PROPOSAL', label: 'Technical proposal' }, { id: 'COMMERCIAL_PROPOSAL', label: 'Commercial proposal' },
  { id: 'SOW', label: 'Statement of work' }, { id: 'ARCHITECTURE_DOC', label: 'Architecture' }, { id: 'FLOW_DIAGRAMS', label: 'Flow diagrams' },
  { id: 'TEST_CASES', label: 'Test cases' }, { id: 'UAT_REPORT', label: 'UAT report' }, { id: 'COMPLETION_CERT', label: 'Completion certificate' },
  { id: 'LESSONS_LEARNED', label: 'Lessons learned' }, { id: 'CONTRACT', label: 'Contract / work order' }, { id: 'OTHER', label: 'Other' },
]
const labelOf = (id: string) => CATEGORIES.find(c => c.id === id)?.label ?? id.replace(/_/g, ' ')

async function openDoc(projectId: number, d: ProjectDocument, inline: boolean) {
  const { data } = await kbApi.projectDocumentBlob(projectId, d.id, inline)
  const url = URL.createObjectURL(data)
  if (inline) window.open(url, '_blank', 'noopener')
  else { const a = document.createElement('a'); a.href = url; a.download = d.original_filename; a.click() }
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

/** The documents of one project, filed by category. View/Download open the real file; "Text" shows what was read from it. */
export function ProjectDocsPanel({ projectId }: { projectId: number }) {
  const [docs, setDocs] = useState<ProjectDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState('COMPLETION_CERT')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [reading, setReading] = useState<ProjectDocument | null>(null)
  const [chunks, setChunks] = useState<{ id: number; section_heading: string | null; chunk_text: string }[] | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { kbApi.listProjectDocuments(projectId).then(r => setDocs(r.data)).finally(() => setLoading(false)) }, [projectId])
  // a document is read in the background after upload: refresh until none is still processing
  useEffect(() => {
    if (!docs.some(d => !d.is_processed && !d.processing_error)) return
    const t = window.setTimeout(() => kbApi.listProjectDocuments(projectId).then(r => setDocs(r.data)), 4000)
    return () => window.clearTimeout(t)
  }, [docs, projectId])

  const groups = useMemo(() => {
    const m = new Map<string, ProjectDocument[]>()
    for (const d of docs) m.set(d.doc_category, [...(m.get(d.doc_category) ?? []), d])
    return [...m.entries()].sort((a, b) => CATEGORIES.findIndex(c => c.id === a[0]) - CATEGORIES.findIndex(c => c.id === b[0]))
  }, [docs])

  async function upload(list: FileList | null) {
    if (!list?.length) return
    setBusy(true); setError('')
    try {
      for (const f of Array.from(list)) {
        const fd = new FormData(); fd.append('file', f); fd.append('doc_category', category)
        const { data } = await kbApi.uploadProjectDocument(projectId, fd)
        setDocs(d => [data, ...d])
      }
    } catch (e) { setError(apiError(e, 'Could not upload the file.')) }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  async function remove(d: ProjectDocument) {
    if (!window.confirm(`Delete ${d.original_filename}?`)) return
    await kbApi.deleteProjectDocument(projectId, d.id)
    setDocs(x => x.filter(y => y.id !== d.id))
    if (reading?.id === d.id) { setReading(null); setChunks(null) }
  }

  async function readText(d: ProjectDocument) {
    if (reading?.id === d.id) { setReading(null); setChunks(null); return }
    setReading(d); setChunks(null)
    try { setChunks((await kbApi.listDocumentChunks(projectId, d.id)).data) } catch { setChunks([]) }
  }

  return (
    <div className="kb-pdocs">
      <div className="kb-pdocs-up">
        <label className="kb-label" htmlFor={`cat-${projectId}`}>File under</label>
        <select id={`cat-${projectId}`} className="kb-select" style={{ width: 'auto', minWidth: '12rem' }} value={category} onChange={e => setCategory(e.target.value)}>
          {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
        </select>
        <input ref={fileRef} type="file" multiple hidden accept=".pdf,.docx,.txt" onChange={e => upload(e.target.files)} />
        <button type="button" className="kb-btn primary" onClick={() => fileRef.current?.click()} disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Upload document
        </button>
        <span className="kb-meta">PDF, Word or text. Stored under <b>{labelOf(category)}</b> for this project.</span>
      </div>
      {error && <p className="kb-err">{error}</p>}

      {loading ? <p className="kb-meta"><Loader2 size={13} className="inline animate-spin" /> Loading documents…</p>
        : docs.length === 0 ? <p className="kb-meta">No documents yet. Choose a category and upload the work order, completion certificate or other files.</p>
        : groups.map(([cat, items]) => (
          <section key={cat} className="kb-pdocs-group">
            <header><FolderOpen size={14} /> {labelOf(cat)} <span className="kb-meta">{items.length}</span></header>
            {items.map(d => (
              <div key={d.id} className="kb-file-row">
                <span className="kb-file-ic"><FileText size={15} /></span>
                <button type="button" className="kb-file-name" onClick={() => openDoc(projectId, d, true)} title="Open the file">{d.original_filename}</button>
                <span className="kb-meta whitespace-nowrap">{[sizeText(d.file_size_bytes), d.page_count ? `${d.page_count} pp` : ''].filter(Boolean).join(' · ')}</span>
                <span className={`kb-pill ${d.processing_error ? 'bad' : d.is_processed ? 'ok' : 'warn'}`}>{d.processing_error ? 'Not readable' : d.is_processed ? 'Indexed' : 'Reading…'}</span>
                <button type="button" className="kb-icon-btn" title="View the file" aria-label={`View ${d.original_filename}`} onClick={() => openDoc(projectId, d, true)}><Eye size={14} /></button>
                <button type="button" className="kb-icon-btn" title="Download" aria-label={`Download ${d.original_filename}`} onClick={() => openDoc(projectId, d, false)}><Download size={14} /></button>
                <button type="button" className={`kb-icon-btn ${reading?.id === d.id ? 'is-on' : ''}`} title="Show the text read from it" aria-label="Show extracted text" onClick={() => readText(d)}><ScanText size={14} /></button>
                <button type="button" className="kb-icon-btn danger" title="Delete" aria-label={`Delete ${d.original_filename}`} onClick={() => remove(d)}><Trash2 size={14} /></button>
              </div>
            ))}
          </section>
        ))}

      {reading && (
        <div className="kb-pdocs-text">
          <p className="kb-label">Text read from {reading.original_filename}</p>
          {chunks === null ? <p className="kb-meta"><Loader2 size={13} className="inline animate-spin" /> Loading…</p>
            : chunks.length === 0 ? <p className="kb-meta">{reading.is_processed ? 'No text could be read from this file.' : 'Still being read. Try again shortly.'}</p>
            : chunks.map(c => (
              <div key={c.id}>
                {c.section_heading && <p className="text-xs font-semibold" style={{ color: 'var(--ink)' }}>{c.section_heading}</p>}
                <p className="kb-meta" style={{ whiteSpace: 'pre-wrap' }}>{c.chunk_text}</p>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
