import { useState, useRef, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Trash2, RefreshCw, Settings, Loader2, Terminal, X, FileText, CheckCircle, AlertTriangle, UploadCloud, Paperclip, Send, Zap } from 'lucide-react'
import {
  estimationProjectsApi,
  type EstimationProject,
  type EstimationProjectListItem,
  type EstimationFeature,
  type EstimationResource,
  type ProgressMessage,
} from '../../api/estimationProjects'
import { documentsApi, type Document as DocumentInfo } from '../../api/documents'
import AssistantMark from '../../components/icons/AssistantMark'
import { ListMagnifyingGlass } from '@phosphor-icons/react'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COMPLEXITY_OPTIONS = [
  { value: null,      label: '—' },
  { value: 'simple',  label: 'Simple' },
  { value: 'medium',  label: 'Medium' },
  { value: 'complex', label: 'Complex' },
] as const

const COMPLEXITY_COLORS: Record<string, string> = {
  simple:  'bg-green-100 text-green-800',
  medium:  'bg-yellow-100 text-yellow-700',
  complex: 'bg-red-100 text-red-700',
}

const LOG_LEVEL_DOT: Record<string, string> = {
  info:    'bg-blue-400',
  working: 'bg-yellow-400 animate-pulse',
  success: 'bg-green-400',
  error:   'bg-red-400',
}
const LOG_LEVEL_TEXT: Record<string, string> = {
  info:    'text-gray-300',
  working: 'text-yellow-300',
  success: 'text-green-300',
  error:   'text-red-400',
}

type TabId = 'features' | 'resources' | 'summary'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n: number): string {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}
function fmtH(n: number): string {
  return n.toFixed(1) + 'h'
}
function pct(n: number): string {
  return (n * 100).toFixed(0) + '%'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ComplexityBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-gray-400 text-xs">—</span>
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${COMPLEXITY_COLORS[value] || 'bg-gray-100 text-gray-600'}`}>
      {value.charAt(0).toUpperCase() + value.slice(1)}
    </span>
  )
}

function ComplexitySelect({
  value,
  onChange,
  disabled,
}: {
  value: string | null
  onChange: (v: string | null) => void
  disabled?: boolean
}) {
  return (
    <select
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
      disabled={disabled}
      className="text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none focus:border-[#014BAA] disabled:opacity-50 w-full"
    >
      {COMPLEXITY_OPTIONS.map((opt) => (
        <option key={String(opt.value)} value={opt.value ?? ''}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

function ProgressLog({
  logs,
  running,
}: {
  logs: ProgressMessage[]
  running: boolean
}) {
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  if (!running && logs.length === 0) return null

  return (
    <div className="bg-gray-900 rounded-lg shadow-sm overflow-hidden mt-3">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-700">
        <Terminal size={14} className="text-green-400" />
        <span className="text-xs font-mono font-semibold text-green-400">AI GENERATION LOG</span>
        {running && <Loader2 size={12} className="animate-spin text-yellow-400 ml-auto" />}
      </div>
      <div ref={logRef} className="px-4 py-3 h-40 overflow-y-auto font-mono text-xs space-y-1.5">
        {logs.map((log, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="text-gray-500 shrink-0 mt-0.5">{log.ts}</span>
            <span className={`w-2 h-2 rounded-full shrink-0 mt-1 ${LOG_LEVEL_DOT[log.level] || 'bg-gray-500'}`} />
            <span className={LOG_LEVEL_TEXT[log.level] || 'text-gray-300'}>{log.message}</span>
          </div>
        ))}
        {running && logs.length === 0 && (
          <div className="flex items-center gap-2 text-yellow-300">
            <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse shrink-0" />
            Initializing...
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Document Picker Modal (for attaching to existing projects)
// ---------------------------------------------------------------------------

function DocumentPickerModal({
  documents,
  onSelect,
  onClose,
}: {
  documents: DocumentInfo[]
  onSelect: (docId: number, filename: string) => void
  onClose: () => void
}) {
  const [mode, setMode] = useState<'select' | 'upload'>('select')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'processing' | 'done' | 'error'>('idle')
  const [uploadedDoc, setUploadedDoc] = useState<DocumentInfo | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  async function handleUpload() {
    if (!file) return
    setUploadState('uploading')
    setErrorMsg(null)
    try {
      const { data: doc } = await documentsApi.upload(file)
      setUploadState('processing')
      pollRef.current = setInterval(async () => {
        try {
          const { data: updated } = await documentsApi.get(doc.id)
          if (updated.status === 'ANALYZED') {
            clearInterval(pollRef.current!); pollRef.current = null
            setUploadState('done')
            setUploadedDoc(updated)
          } else if (updated.status === 'FAILED') {
            clearInterval(pollRef.current!); pollRef.current = null
            setUploadState('error')
            setErrorMsg('Document analysis failed')
          }
        } catch { /* ignore poll errors */ }
      }, 2500)
    } catch (err: any) {
      setUploadState('error')
      setErrorMsg(err.response?.data?.detail || 'Upload failed')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-[#0A2150]">Attach Document</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {/* Mode tabs */}
        <div className="flex border-b border-gray-100">
          {(['select', 'upload'] as const).map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                mode === m ? 'text-[#014BAA] border-b-2 border-[#014BAA]' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m === 'select' ? 'Select Existing' : 'Upload New File'}
            </button>
          ))}
        </div>

        <div className="px-6 py-5">
          {mode === 'select' ? (
            <div className="space-y-4">
              {documents.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">No analyzed documents found. Use "Upload New File".</p>
              ) : (
                <select
                  value={selectedId ?? ''}
                  onChange={(e) => setSelectedId(e.target.value === '' ? null : Number(e.target.value))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#014BAA]"
                >
                  <option value="">— Select a document —</option>
                  {documents.map(doc => (
                    <option key={doc.id} value={doc.id}>{doc.original_filename}</option>
                  ))}
                </select>
              )}
              <div className="flex gap-3 pt-1">
                <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
                <button
                  onClick={() => { const d = documents.find(x => x.id === selectedId); if (d) onSelect(d.id, d.original_filename) }}
                  disabled={!selectedId}
                  className="flex-1 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C] disabled:opacity-50"
                >
                  Attach
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {errorMsg && (
                <div className="bg-red-50 text-red-700 border border-red-200 rounded px-3 py-2 text-sm">{errorMsg}</div>
              )}

              {uploadState === 'idle' && (
                <>
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-[#014BAA] hover:bg-blue-50/30 transition-colors"
                  >
                    <UploadCloud size={32} className="mx-auto text-gray-400 mb-2" />
                    <p className="text-sm font-medium text-gray-700">{file ? file.name : 'Click to select a file'}</p>
                    <p className="text-xs text-gray-400 mt-1">PDF, DOCX, or TXT</p>
                    <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                  </div>
                  <div className="flex gap-3">
                    <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
                    <button
                      onClick={handleUpload}
                      disabled={!file}
                      className="flex-1 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C] disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      <UploadCloud size={14} /> Upload & Analyze
                    </button>
                  </div>
                </>
              )}

              {(uploadState === 'uploading' || uploadState === 'processing') && (
                <div className="text-center py-8">
                  <Loader2 size={32} className={`mx-auto mb-3 animate-spin ${uploadState === 'processing' ? 'text-yellow-500' : 'text-[#014BAA]'}`} />
                  <p className="text-sm font-semibold text-gray-700">
                    {uploadState === 'uploading' ? `Uploading ${file?.name}…` : 'Analyzing document with AI…'}
                  </p>
                  {uploadState === 'processing' && <p className="text-xs text-gray-400 mt-1">This may take a minute</p>}
                </div>
              )}

              {uploadState === 'done' && uploadedDoc && (
                <div className="space-y-4">
                  <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 flex items-center gap-3">
                    <CheckCircle size={18} className="text-green-600 shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-green-800">{uploadedDoc.original_filename}</p>
                      <p className="text-xs text-green-600">Analyzed successfully</p>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
                    <button
                      onClick={() => onSelect(uploadedDoc.id, uploadedDoc.original_filename)}
                      className="flex-1 py-2 rounded-lg bg-[#1F7A56] text-white text-sm font-medium hover:bg-[#186446] flex items-center justify-center gap-2"
                    >
                      <CheckCircle size={14} /> Attach to Project
                    </button>
                  </div>
                </div>
              )}

              {uploadState === 'error' && (
                <div className="flex gap-3">
                  <button onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
                  <button
                    onClick={() => { setUploadState('idle'); setErrorMsg(null); setFile(null) }}
                    className="flex-1 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C]"
                  >
                    Try Again
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// New Project Modal
// ---------------------------------------------------------------------------

function NewProjectModal({
  onClose,
  onCreate,
  documents: initialDocuments,
}: {
  onClose: () => void
  onCreate: (name: string, documentId: number | null) => Promise<void>
  documents: DocumentInfo[]
}) {
  const [name, setName] = useState('')
  const [docId, setDocId] = useState<number | null>(null)
  const [docFilename, setDocFilename] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [docMode, setDocMode] = useState<'select' | 'upload'>('select')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadState, setUploadState] = useState<'idle' | 'uploading' | 'processing' | 'done'>('idle')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [docs, setDocs] = useState(initialDocuments)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  async function handleUploadDoc() {
    if (!uploadFile) return
    setUploadState('uploading')
    setUploadError(null)
    try {
      const { data: doc } = await documentsApi.upload(uploadFile)
      setUploadState('processing')
      pollRef.current = setInterval(async () => {
        try {
          const { data: updated } = await documentsApi.get(doc.id)
          if (updated.status === 'ANALYZED') {
            clearInterval(pollRef.current!); pollRef.current = null
            setUploadState('done')
            setDocId(updated.id)
            setDocFilename(updated.original_filename)
            setDocs(prev => [updated, ...prev])
          } else if (updated.status === 'FAILED') {
            clearInterval(pollRef.current!); pollRef.current = null
            setUploadState('idle')
            setUploadError('Document analysis failed. Try again.')
          }
        } catch { /* ignore */ }
      }, 2500)
    } catch (err: any) {
      setUploadState('idle')
      setUploadError(err.response?.data?.detail || 'Upload failed')
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Project name is required'); return }
    setLoading(true)
    setError(null)
    try {
      await onCreate(name.trim(), docId)
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-[#0A2150]">New Estimation Project</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
          {error && (
            <div className="bg-red-50 text-red-700 border border-red-200 rounded px-3 py-2 text-sm">{error}</div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Project Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Hospital Management System"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#014BAA]"
              autoFocus
            />
          </div>

          {/* Document section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">
                Attach SRS Document <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <div className="flex text-xs rounded-lg overflow-hidden border border-gray-200">
                <button type="button" onClick={() => setDocMode('select')}
                  className={`px-2.5 py-1 ${docMode === 'select' ? 'bg-[#014BAA] text-white' : 'text-gray-500 hover:bg-gray-50'}`}>
                  Select
                </button>
                <button type="button" onClick={() => setDocMode('upload')}
                  className={`px-2.5 py-1 ${docMode === 'upload' ? 'bg-[#014BAA] text-white' : 'text-gray-500 hover:bg-gray-50'}`}>
                  Upload
                </button>
              </div>
            </div>

            {docMode === 'select' ? (
              <select
                value={docId ?? ''}
                onChange={(e) => {
                  const id = e.target.value === '' ? null : Number(e.target.value)
                  setDocId(id)
                  setDocFilename(id ? (docs.find(d => d.id === id)?.original_filename ?? null) : null)
                }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#014BAA]"
              >
                <option value="">— No document —</option>
                {docs.map((doc) => (
                  <option key={doc.id} value={doc.id}>{doc.original_filename}</option>
                ))}
              </select>
            ) : (
              <div>
                {uploadError && (
                  <p className="text-xs text-red-600 mb-2">{uploadError}</p>
                )}
                {uploadState === 'done' && docFilename ? (
                  <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 flex items-center gap-2 text-sm">
                    <CheckCircle size={14} className="text-green-600 shrink-0" />
                    <span className="text-green-800 font-medium truncate">{docFilename}</span>
                    <button type="button" onClick={() => { setUploadState('idle'); setUploadFile(null); setDocId(null); setDocFilename(null) }}
                      className="ml-auto text-gray-400 hover:text-gray-600 shrink-0"><X size={13} /></button>
                  </div>
                ) : (uploadState === 'uploading' || uploadState === 'processing') ? (
                  <div className="border border-gray-200 rounded-lg px-3 py-3 flex items-center gap-2 text-sm text-gray-600">
                    <Loader2 size={14} className={`animate-spin shrink-0 ${uploadState === 'processing' ? 'text-yellow-500' : 'text-[#014BAA]'}`} />
                    {uploadState === 'uploading' ? `Uploading ${uploadFile?.name}…` : 'Analyzing document…'}
                  </div>
                ) : (
                  <div className="flex gap-2 min-w-0">
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      className="flex-1 min-w-0 flex items-center gap-2 border border-dashed border-gray-300 rounded-lg px-3 py-2 cursor-pointer hover:border-[#014BAA] hover:bg-blue-50/20 text-sm text-gray-500 transition-colors overflow-hidden"
                    >
                      <UploadCloud size={15} className="shrink-0 text-gray-400" />
                      <span className="truncate min-w-0">{uploadFile ? uploadFile.name : 'Choose file (PDF, DOCX, TXT)'}</span>
                      <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" className="hidden"
                        onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
                    </div>
                    <button
                      type="button"
                      onClick={handleUploadDoc}
                      disabled={!uploadFile}
                      className="px-3 py-2 rounded-lg bg-[#014BAA] text-white text-xs font-medium hover:bg-[#013D8C] disabled:opacity-40 shrink-0"
                    >
                      Upload
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || uploadState === 'uploading' || uploadState === 'processing'}
              className="flex-1 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C] disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? <><Loader2 size={14} className="animate-spin" /> Creating…</> : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Settings Panel
// ---------------------------------------------------------------------------

function SettingsPanel({
  project,
  onSave,
  saving,
  aiToolsFactor,
  onAiToolsFactorChange,
}: {
  project: EstimationProject
  onSave: (updates: Record<string, number>) => void
  saving: boolean
  aiToolsFactor: number
  onAiToolsFactorChange: (v: number) => void
}) {
  const [vals, setVals] = useState({
    complexity_pct: (project.complexity_pct * 100).toFixed(0),
    unit_testing_pct: (project.unit_testing_pct * 100).toFixed(0),
    rework_pct: (project.rework_pct * 100).toFixed(0),
    pm_pct: (project.pm_pct * 100).toFixed(0),
    design_arch_pct: (project.design_arch_pct * 100).toFixed(0),
    spec_uiux_pct: (project.spec_uiux_pct * 100).toFixed(0),
    dev_buffer_pct: (project.dev_buffer_pct * 100).toFixed(0),
    margin_pct: (project.margin_pct * 100).toFixed(0),
    infra_cost: project.infra_cost.toFixed(0),
  })

  // Refresh when project changes
  useEffect(() => {
    setVals({
      complexity_pct: (project.complexity_pct * 100).toFixed(0),
      unit_testing_pct: (project.unit_testing_pct * 100).toFixed(0),
      rework_pct: (project.rework_pct * 100).toFixed(0),
      pm_pct: (project.pm_pct * 100).toFixed(0),
      design_arch_pct: (project.design_arch_pct * 100).toFixed(0),
      spec_uiux_pct: (project.spec_uiux_pct * 100).toFixed(0),
      dev_buffer_pct: (project.dev_buffer_pct * 100).toFixed(0),
      margin_pct: (project.margin_pct * 100).toFixed(0),
      infra_cost: project.infra_cost.toFixed(0),
    })
  }, [project.id])

  function handleSave() {
    onSave({
      complexity_pct:   Number(vals.complexity_pct)   / 100,
      unit_testing_pct: Number(vals.unit_testing_pct) / 100,
      rework_pct:       Number(vals.rework_pct)       / 100,
      pm_pct:           Number(vals.pm_pct)           / 100,
      design_arch_pct:  Number(vals.design_arch_pct)  / 100,
      spec_uiux_pct:    Number(vals.spec_uiux_pct)    / 100,
      dev_buffer_pct:   Number(vals.dev_buffer_pct)   / 100,
      margin_pct:       Number(vals.margin_pct)       / 100,
      infra_cost:       Number(vals.infra_cost),
    })
  }

  const pctField = (
    key: keyof typeof vals,
    label: string,
    hint?: string,
  ) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-0.5">{label}</label>
      {hint && <p className="text-[10px] text-gray-400 mb-1">{hint}</p>}
      <div className="flex items-center gap-1">
        <input
          type="number"
          min={0}
          max={200}
          value={vals[key]}
          onChange={(e) => setVals(v => ({ ...v, [key]: e.target.value }))}
          className="w-16 border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:border-[#014BAA]"
        />
        <span className="text-xs text-gray-500">{key === 'infra_cost' ? '₹' : '%'}</span>
      </div>
    </div>
  )

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mt-4">
      <h3 className="text-sm font-semibold text-[#0A2150] mb-4 flex items-center gap-2">
        <Settings size={15} /> Project Settings
      </h3>
      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-500">Dev Adjustments</p>
          {pctField('complexity_pct', 'Complexity Buffer', 'Applied to base hours')}
          {pctField('unit_testing_pct', 'Unit Testing')}
          {pctField('rework_pct', 'Rework Buffer')}
        </div>
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-500">Project Overheads</p>
          {pctField('pm_pct', 'Project Management')}
          {pctField('design_arch_pct', 'Design & Architecture')}
          {pctField('spec_uiux_pct', 'Spec / UI-UX')}
          {pctField('dev_buffer_pct', 'Dev Buffer')}
        </div>
        <div className="space-y-3">
          <p className="text-xs font-semibold text-gray-500">Cost Settings</p>
          {pctField('margin_pct', 'Profit Margin')}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5">Infrastructure Cost (₹)</label>
            <input
              type="number"
              min={0}
              value={vals.infra_cost}
              onChange={(e) => setVals(v => ({ ...v, infra_cost: e.target.value }))}
              className="w-32 border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:border-[#014BAA]"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-0.5 flex items-center gap-1">
              <Zap size={11} className="text-purple-500" /> AI Tools Factor
            </label>
            <p className="text-[10px] text-gray-400 mb-1">Hours multiplier when using Claude / Copilot / Codex</p>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={10}
                max={80}
                step={5}
                value={Math.round(aiToolsFactor * 100)}
                onChange={e => onAiToolsFactorChange(Number(e.target.value) / 100)}
                className="w-24 accent-purple-600"
              />
              <span className="text-xs font-semibold text-purple-700 w-20">
                {Math.round(aiToolsFactor * 100)}% of manual
                <span className="text-gray-400 font-normal"> ({Math.round((1 - aiToolsFactor) * 100)}% faster)</span>
              </span>
            </div>
          </div>
        </div>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 bg-[#014BAA] text-white text-sm rounded-lg font-medium hover:bg-[#013D8C] disabled:opacity-50 flex items-center gap-2"
        >
          {saving ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : <><RefreshCw size={13} /> Save & Recalculate</>}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generation Wizard Modal
// ---------------------------------------------------------------------------

const PLATFORM_OPTIONS = [
  { id: 'web'    as const, label: 'Web App',        icon: '🌐', desc: 'Browser-based application' },
  { id: 'mobile' as const, label: 'Mobile App',     icon: '📱', desc: 'iOS & Android application' },
  { id: 'both'   as const, label: 'Web + Mobile',   icon: '💻', desc: 'Both web and mobile platforms' },
]

type Platform = 'web' | 'mobile' | 'both'

const STACK_LAYERS: Record<string, { key: string; label: string; options: string[] }[]> = {
  web: [
    { key: 'frontend', label: 'Frontend Framework', options: ['React', 'Vue.js', 'Angular', 'Next.js', 'Nuxt.js', 'Svelte'] },
    { key: 'backend',  label: 'Backend / API',      options: ['Node.js / Express', 'Python / FastAPI', 'Python / Django', 'Java / Spring Boot', '.NET Core', 'Go / Gin'] },
    { key: 'database', label: 'Database',            options: ['PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Firebase', 'SQLite'] },
  ],
  mobile: [
    { key: 'mobile_framework', label: 'Mobile Framework', options: ['React Native', 'Flutter', 'Android (Kotlin)', 'iOS (Swift)', 'Ionic'] },
    { key: 'backend',          label: 'Backend / API',    options: ['Node.js / Express', 'Python / FastAPI', 'Python / Django', 'Java / Spring Boot', 'Firebase'] },
    { key: 'database',         label: 'Database',         options: ['PostgreSQL', 'MySQL', 'MongoDB', 'Firebase', 'SQLite', 'Realm'] },
  ],
}

function getLayers(platform: Platform) {
  if (platform === 'both') {
    const mobile = STACK_LAYERS.mobile.find(l => l.key === 'mobile_framework')!
    return [mobile, ...STACK_LAYERS.web]
  }
  return STACK_LAYERS[platform] ?? STACK_LAYERS.web
}

function GenerationWizardModal({
  onClose,
  onGenerate,
}: {
  onClose: () => void
  onGenerate: (platform: Platform, techStack: Record<string, string[]>, model: string, temperature: number, seed: number | undefined) => void
}) {
  const [step, setStep]         = useState<1 | 2 | 3>(1)
  const [platform, setPlatform] = useState<Platform | null>(null)
  const [selected, setSelected] = useState<Record<string, string[]>>({})
  const [customs, setCustoms]   = useState<Record<string, string>>({})
  // Step 3 — AI settings
  const [models, setModels]         = useState<string[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [deterministic, setDeterministic] = useState(true) // default: consistent output

  async function loadModels() {
    if (models.length > 0) return
    setModelsLoading(true)
    try {
      const { data } = await estimationProjectsApi.listModels()
      setModels(data.models)
      if (data.models.length > 0) setSelectedModel(data.models[0])
    } finally {
      setModelsLoading(false)
    }
  }

  function goToStep3() {
    setStep(3)
    loadModels()
  }

  function toggleChip(layer: string, value: string) {
    setSelected(prev => {
      const cur = prev[layer] ?? []
      return { ...prev, [layer]: cur.includes(value) ? cur.filter(x => x !== value) : [...cur, value] }
    })
  }

  function addCustom(layer: string) {
    const val = customs[layer]?.trim()
    if (!val) return
    setSelected(prev => ({ ...prev, [layer]: [...(prev[layer] ?? []), val] }))
    setCustoms(prev => ({ ...prev, [layer]: '' }))
  }

  function handleGenerate() {
    if (!platform) return
    const temperature = deterministic ? 0.0 : 0.7
    const seed        = deterministic ? 42   : undefined
    onGenerate(platform, selected, selectedModel, temperature, seed)
  }

  const stepLabels: Record<number, string> = { 1: 'Choose platform', 2: 'Select tech stack', 3: 'AI settings' }
  const layers = platform ? getLayers(platform) : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100" style={{ background: 'var(--zx-head)' }}>
          <div className="flex items-center gap-3">
            <ListMagnifyingGlass size={18} className="text-[#8FB3F2]" />
            <div>
              <h2 className="text-sm font-semibold text-white">Analyse &amp; Generate Features</h2>
              <p className="text-[11px] text-gray-400">Step {step} of 3 — {stepLabels[step]}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors"><X size={16} /></button>
        </div>

        {/* Step indicator */}
        <div className="flex h-1">
          <div className="flex-1 transition-all duration-300" style={{ background: '#014BAA' }} />
          <div className="flex-1 transition-all duration-300" style={{ background: step >= 2 ? '#014BAA' : '#e5e7eb' }} />
          <div className="flex-1 transition-all duration-300" style={{ background: step === 3 ? '#014BAA' : '#e5e7eb' }} />
        </div>

        <div className="p-6">
          {/* ── Step 1: Platform ── */}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">What type of application is this project?</p>
              <div className="grid grid-cols-3 gap-3">
                {PLATFORM_OPTIONS.map(opt => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setPlatform(opt.id)}
                    className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                      platform === opt.id
                        ? 'border-[#014BAA] bg-blue-50 shadow-sm'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <span className="text-2xl">{opt.icon}</span>
                    <span className={`text-xs font-semibold ${platform === opt.id ? 'text-[#0A2150]' : 'text-gray-600'}`}>{opt.label}</span>
                    <span className="text-[10px] text-gray-400 text-center leading-tight">{opt.desc}</span>
                  </button>
                ))}
              </div>
              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  disabled={!platform}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C] disabled:opacity-40 transition-colors"
                >
                  Next: Tech Stack →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Tech Stack ── */}
          {step === 2 && platform && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                Select the tech stack for your <strong>{PLATFORM_OPTIONS.find(p => p.id === platform)?.label}</strong>.
                <span className="text-gray-400 ml-1">Skip layers you don't need.</span>
              </p>
              <div className="space-y-4 max-h-72 overflow-y-auto pr-1">
                {layers.map(layer => (
                  <div key={layer.key}>
                    <p className="text-[11px] font-semibold text-gray-500 mb-2">{layer.label}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {layer.options.map(opt => {
                        const isSelected = (selected[layer.key] ?? []).includes(opt)
                        return (
                          <button key={opt} type="button" onClick={() => toggleChip(layer.key, opt)}
                            className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-all ${
                              isSelected
                                ? 'bg-[var(--zx-head)] text-white border-[var(--zx-head)]'
                                : 'bg-white text-gray-600 border-gray-300 hover:border-[#014BAA] hover:text-[#014BAA]'
                            }`}>
                            {isSelected && <span className="mr-1">✓</span>}{opt}
                          </button>
                        )
                      })}
                      {/* Custom input */}
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={customs[layer.key] ?? ''}
                          onChange={e => setCustoms(prev => ({ ...prev, [layer.key]: e.target.value }))}
                          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom(layer.key) } }}
                          placeholder="Custom…"
                          className="text-xs px-2.5 py-1.5 border border-dashed border-gray-300 rounded-full w-24 focus:outline-none focus:border-[#014BAA] placeholder-gray-400"
                        />
                        {(customs[layer.key] ?? '').trim() && (
                          <button type="button" onClick={() => addCustom(layer.key)}
                            className="text-[10px] px-2 py-1.5 rounded-full bg-[#1F7A56] text-white font-medium">
                            + Add
                          </button>
                        )}
                      </div>
                    </div>
                    {/* Show custom-added chips */}
                    {(selected[layer.key] ?? []).filter(v => !layer.options.includes(v)).map(v => (
                      <span key={v} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-full bg-[var(--zx-head)] text-white border border-[var(--zx-head)] mt-1.5 mr-1.5 font-medium">
                        ✓ {v}
                        <button type="button" onClick={() => toggleChip(layer.key, v)} className="ml-0.5 opacity-60 hover:opacity-100">×</button>
                      </span>
                    ))}
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <button type="button" onClick={() => setStep(1)}
                  className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1">
                  ← Back
                </button>
                <button type="button" onClick={goToStep3}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg bg-[#014BAA] text-white text-sm font-medium hover:bg-[#013D8C] transition-colors">
                  Next: AI Settings →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: AI Settings ── */}
          {step === 3 && (
            <div className="space-y-5">
              {/* Model selector */}
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-2">AI Model</p>
                {modelsLoading ? (
                  <div className="flex items-center gap-2 text-gray-400 text-sm">
                    <Loader2 size={14} className="animate-spin" /> Loading models from Ollama…
                  </div>
                ) : models.length === 0 ? (
                  <p className="text-sm text-red-500">No models found. Make sure Ollama is running and a model is pulled.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {models.map(m => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setSelectedModel(m)}
                        className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all ${
                          selectedModel === m
                            ? 'border-[#014BAA] bg-[#014BAA] text-white shadow-sm'
                            : 'border-gray-300 text-gray-600 hover:border-[#014BAA] hover:text-[#014BAA]'
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Consistency toggle */}
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-3">Output Consistency</p>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setDeterministic(true)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      deterministic
                        ? 'border-[#014BAA] bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <p className={`text-sm font-semibold mb-1 ${deterministic ? 'text-[#0A2150]' : 'text-gray-600'}`}>
                      🔒 Consistent
                    </p>
                    <p className="text-[11px] text-gray-400 leading-tight">
                      Same SRS always produces the same features & hours. Best for estimates you need to reproduce.
                    </p>
                    {deterministic && <p className="text-[10px] text-[#014BAA] mt-1.5 font-medium">temperature=0.0 · seed=42</p>}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeterministic(false)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      !deterministic
                        ? 'border-[#1F7A56] bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <p className={`text-sm font-semibold mb-1 ${!deterministic ? 'text-[#1A6B4A]' : 'text-gray-600'}`}>
                      🎲 Creative
                    </p>
                    <p className="text-[11px] text-gray-400 leading-tight">
                      Each run may produce different feature breakdowns. Good for exploring alternative estimates.
                    </p>
                    {!deterministic && <p className="text-[10px] text-[#1F7A56] mt-1.5 font-medium">temperature=0.7 · random seed</p>}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                <button type="button" onClick={() => setStep(2)}
                  className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1">
                  ← Back
                </button>
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={models.length > 0 && !selectedModel}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg text-white text-sm font-medium disabled:opacity-40 transition-colors"
                  style={{ background: 'var(--zx-head)' }}
                >
                  <ListMagnifyingGlass size={15} /> Analyse &amp; Generate Features
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Features Tab
// ---------------------------------------------------------------------------

function FeaturesTab({
  project,
  onProjectUpdate,
  generating,
  onGenerate,
  genLogs,
  aiToolsFactor,
  moduleFactors,
  setModuleFactors,
}: {
  project: EstimationProject
  onProjectUpdate: (p: EstimationProject) => void
  generating: boolean
  onGenerate: (platform: Platform, techStack: Record<string, string[]>, model: string, temperature: number, seed: number | undefined) => void
  genLogs: ProgressMessage[]
  aiToolsFactor: number
  moduleFactors: Record<string, number>
  setModuleFactors: React.Dispatch<React.SetStateAction<Record<string, number>>>
}) {
  const [saving, setSaving] = useState<number | null>(null)
  const [addingRow, setAddingRow] = useState(false)
  const [newFeature, setNewFeature] = useState('')
  const [newModule, setNewModule] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [addingInModule, setAddingInModule] = useState<string | null>(null)
  const [addingInSubModule, setAddingInSubModule] = useState<{ mod: string; sub: string } | null>(null)
  const [newSubModuleInput, setNewSubModuleInput] = useState('')
  const [collapsedModules, setCollapsedModules] = useState<Set<string>>(() =>
    new Set((project.features ?? []).map(f => f.module || 'General'))
  )
  const [collapsedSubModules, setCollapsedSubModules] = useState<Set<string>>(() => {
    const keys = new Set<string>()
    for (const f of project.features ?? []) {
      if (f.sub_module) keys.add(`${f.module || 'General'}::${f.sub_module}`)
    }
    return keys
  })

  const [showWizard, setShowWizard] = useState(false)

  // AI Advisor chat state
  const [showChat, setShowChat] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatLogs, setChatLogs] = useState<ProgressMessage[]>([])
  const [showModuleBreakdown, setShowModuleBreakdown] = useState(false)
  const chatInputRef = useRef<HTMLTextAreaElement>(null)
  const chatPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  type ChatMsg = { role: 'user' | 'ai'; text: string; ts: string }
  const [chatHistory, setChatHistory] = useState<ChatMsg[]>([])

  // Reset collapsed state when project changes
  useEffect(() => {
    setCollapsedModules(new Set((project.features ?? []).map(f => f.module || 'General')))
    const keys = new Set<string>()
    for (const f of project.features ?? []) {
      if (f.sub_module) keys.add(`${f.module || 'General'}::${f.sub_module}`)
    }
    setCollapsedSubModules(keys)
  }, [project.id])

  // Reset chat history when project changes
  useEffect(() => {
    setChatHistory([])
    setChatLogs([])
    setChatLoading(false)
    if (chatPollRef.current) { clearInterval(chatPollRef.current); chatPollRef.current = null }
  }, [project.id])

  // Auto-scroll chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatHistory, chatLogs])

  function getModuleFactor(mod: string) {
    return moduleFactors[mod] ?? aiToolsFactor
  }

  const CHAT_EXAMPLES = [
    'Reduce total cost to under ₹5 lakhs',
    'POC only — remove PM, BA, UX',
    'Simplify all UI to basic, keep API & data model',
    'Cut scope by 30%, focus on core features only',
  ]

  async function handleChatSubmit() {
    if (!chatInput.trim() || chatLoading) return
    const msg = chatInput.trim()
    const ts = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit' })
    setChatHistory(h => [...h, { role: 'user', text: msg, ts }])
    setChatInput('')
    setChatLoading(true)
    setChatLogs([])

    try {
      await estimationProjectsApi.chatReestimate(project.id, msg)
      // Poll chat progress
      chatPollRef.current = setInterval(async () => {
        try {
          const { data } = await estimationProjectsApi.getChatProgress(project.id)
          setChatLogs(data.messages)
          const last = data.messages[data.messages.length - 1]
          if (!last) return
          if (last.level === 'success' && last.message.toLowerCase().startsWith('complete')) {
            clearInterval(chatPollRef.current!); chatPollRef.current = null
            const { data: result } = await estimationProjectsApi.getChatResult(project.id)
            if (result.project) onProjectUpdate(result.project)
            const aiTs = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit' })
            setChatHistory(h => [...h, { role: 'ai', text: result.advice ?? `Updated ${result.changed_count ?? '?'} features.`, ts: aiTs }])
            setChatLogs([])
            setChatLoading(false)
          } else if (last.level === 'error') {
            clearInterval(chatPollRef.current!); chatPollRef.current = null
            const aiTs = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit' })
            setChatHistory(h => [...h, { role: 'ai', text: `⚠ ${last.message}`, ts: aiTs }])
            setChatLogs([])
            setChatLoading(false)
          }
        } catch { /* ignore poll errors */ }
      }, 1500)
    } catch (err: any) {
      const aiTs = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit' })
      setChatHistory(h => [...h, { role: 'ai', text: `Error: ${err.response?.data?.detail || 'Failed to start re-estimation'}`, ts: aiTs }])
      setChatLoading(false)
    }
  }

  async function handleComplexityChange(
    feature: EstimationFeature,
    field: keyof Pick<EstimationFeature, 'data_model_complexity' | 'api_complexity' | 'business_rules_complexity' | 'ui_complexity'>,
    value: string | null,
  ) {
    setSaving(feature.id)
    try {
      const { data } = await estimationProjectsApi.updateFeature(project.id, feature.id, {
        [field]: value,
      })
      onProjectUpdate(data)
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(null)
    }
  }

  async function handleFixedHoursChange(feature: EstimationFeature, value: number) {
    setSaving(feature.id)
    try {
      const { data } = await estimationProjectsApi.updateFeature(project.id, feature.id, {
        fixed_hours: value,
      })
      onProjectUpdate(data)
    } finally {
      setSaving(null)
    }
  }

  async function handleDelete(featureId: number) {
    setDeletingId(featureId)
    try {
      const { data } = await estimationProjectsApi.deleteFeature(project.id, featureId)
      onProjectUpdate(data)
    } catch (err) {
      console.error(err)
    } finally {
      setDeletingId(null)
    }
  }

  async function handleAddFeature() {
    if (!newFeature.trim()) return
    try {
      const { data } = await estimationProjectsApi.addFeature(project.id, {
        feature: newFeature.trim(),
        module: newModule.trim() || null,
        sort_order: project.features.length,
      })
      onProjectUpdate(data)
      setNewFeature('')
      setNewModule('')
      setAddingRow(false)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleAddFeatureInContext(mod: string, sub: string) {
    if (!newFeature.trim()) return
    try {
      const { data } = await estimationProjectsApi.addFeature(project.id, {
        feature: newFeature.trim(),
        module: mod || null,
        sub_module: sub || null,
        sort_order: project.features.length,
      })
      onProjectUpdate(data)
      setNewFeature('')
      setAddingInSubModule(null)
    } catch (err) {
      console.error(err)
    }
  }

  const features = project.features ?? []

  const totalDevH = features.reduce((s, f) => s + f.total_dev_hours, 0)
  const totalQaH  = features.reduce((s, f) => s + f.total_qa_hours,  0)
  const totalH    = features.reduce((s, f) => s + f.total_hours,     0)

  // Compute AI hours (needed for both summary and table render)
  const modules = [...new Set(features.map(f => f.module || 'General'))]
  const moduleRows = modules.map(mod => {
    const mFeats = features.filter(f => (f.module || 'General') === mod)
    const mDevH = mFeats.reduce((s, f) => s + f.total_dev_hours, 0)
    const mQaH  = mFeats.reduce((s, f) => s + f.total_qa_hours, 0)
    const factor = getModuleFactor(mod)
    const aiDevH   = mDevH * factor
    const aiQaH    = aiDevH * 0.40
    const aiTotalH = aiDevH + aiQaH
    return { mod, mDevH, mQaH, manualH: mDevH + mQaH, factor, aiDevH, aiQaH, aiTotalH }
  })
  const aiTotalDevH = moduleRows.reduce((s, r) => s + r.aiDevH, 0)
  const aiTotalQaH  = moduleRows.reduce((s, r) => s + r.aiQaH, 0)
  const aiGrandH    = aiTotalDevH + aiTotalQaH
  const savedH      = totalH - aiGrandH

  return (
    <div className="flex flex-col gap-3">

      {/* ── Top actions bar ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-medium px-2 py-1 bg-white border border-gray-200 rounded-lg">
            {features.length} features
          </span>
          {project.document_id && (
            <button
              onClick={() => setShowWizard(true)}
              disabled={generating}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--zx-head)] text-white text-xs rounded-lg font-medium hover:brightness-110 disabled:opacity-50 transition-colors"
            >
              {generating ? <><Loader2 size={12} className="animate-spin" /> Analysing Document…</> : <><ListMagnifyingGlass size={14} /> Analyse &amp; Generate Features</>}
            </button>
          )}
          {features.length > 0 && (
            <button
              onClick={() => setShowChat(v => !v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg font-medium border transition-colors ${
                showChat ? 'bg-[#014BAA] text-white border-[#014BAA]' : 'bg-white text-[#014BAA] border-[#014BAA]/40 hover:bg-[#014BAA]/10'
              }`}
            >
              <AssistantMark size={14} /> AI Advisor
            </button>
          )}
          {!project.document_id && features.length === 0 && (
            <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-1 rounded-lg">
              Attach a document to use AI generation
            </span>
          )}
        </div>
        <button
          onClick={() => setAddingRow(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1F7A56] text-white text-xs rounded-lg font-medium hover:bg-[#186446] transition-colors"
        >
          <Plus size={12} /> Add Feature
        </button>
      </div>

      {/* ── AI Advisor chat panel ── */}
      {showChat && (
        <div className="rounded-xl border overflow-hidden shadow-lg" style={{ borderColor: 'rgba(143, 179, 242, 0.25)', background: 'linear-gradient(135deg, #021434 0%, #03255A 100%)' }}>
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10">
            <div className="zx-ai-plate w-8 h-8 rounded-lg">
              <AssistantMark size={19} />
            </div>
            <span className="text-xs font-semibold text-white">AI Advisor</span>
            <span className="text-[10px] text-[#A9C4F5]/70">— re-estimate by natural language instruction</span>
            {chatLoading && (
              <div className="flex items-center gap-1.5 ml-2 text-yellow-400">
                <Loader2 size={11} className="animate-spin" />
                <span className="text-[10px]">Working…</span>
              </div>
            )}
            <button onClick={() => setShowChat(false)} className="ml-auto p-1 rounded hover:bg-purple-800/50 text-purple-500 hover:text-purple-200 transition-colors">
              <X size={13} />
            </button>
          </div>

          <div className="p-4 space-y-3">
            {/* Example chips */}
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[10px] text-purple-500 self-center mr-1">Try:</span>
              {CHAT_EXAMPLES.map(ex => (
                <button key={ex} onClick={() => setChatInput(ex)}
                  className="text-[10px] px-2.5 py-1 rounded-full bg-purple-900/60 text-purple-300 hover:bg-purple-700 hover:text-white transition-colors border border-purple-700/60">
                  {ex}
                </button>
              ))}
            </div>

            {/* Conversation thread */}
            {chatHistory.length > 0 && (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1 rounded-lg bg-black/20 p-3">
                {chatHistory.map((msg, i) => (
                  <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {msg.role === 'ai' && (
                      <div className="zx-ai-plate w-7 h-7 rounded-full shrink-0 mt-0.5">
                        <AssistantMark size={16} />
                      </div>
                    )}
                    <div className={`max-w-[80%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-purple-600 text-white rounded-br-sm'
                        : 'bg-purple-950/80 text-purple-100 border border-purple-700/50 rounded-bl-sm'
                    }`}>
                      {msg.text}
                      <span className="block text-[9px] mt-1 opacity-40">{msg.ts}</span>
                    </div>
                    {msg.role === 'user' && (
                      <div className="w-5 h-5 rounded-full bg-[#014BAA] flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[9px] text-white font-semibold">U</span>
                      </div>
                    )}
                  </div>
                ))}
                {/* Live streaming log */}
                {chatLoading && chatLogs.length > 0 && (
                  <div className="flex gap-2">
                    <div className="w-5 h-5 rounded-full bg-purple-600 flex items-center justify-center shrink-0 mt-0.5">
                      <Loader2 size={10} className="animate-spin text-white" />
                    </div>
                    <div className="bg-black/30 border border-purple-800/50 rounded-xl rounded-bl-sm px-3 py-2 space-y-0.5 flex-1">
                      {chatLogs.map((log, j) => (
                        <div key={j} className={`flex items-center gap-1.5 text-[10px] font-mono ${LOG_LEVEL_TEXT[log.level] || 'text-gray-300'}`}>
                          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${LOG_LEVEL_DOT[log.level] || 'bg-gray-400'}`} />
                          <span className="opacity-50">{log.ts}</span>
                          <span>{log.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div ref={chatBottomRef} />
              </div>
            )}

            {/* Input row */}
            <div className="flex gap-2">
              <textarea
                ref={chatInputRef}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatSubmit() } }}
                placeholder="e.g. 'Reduce cost to ₹5 lakhs' or 'POC only, remove PM and UX'"
                rows={2}
                disabled={chatLoading}
                className="flex-1 bg-black/30 border border-purple-700/60 rounded-lg px-3 py-2 text-xs text-purple-100 placeholder-purple-600 focus:outline-none focus:border-purple-500 resize-none disabled:opacity-50"
              />
              <button onClick={handleChatSubmit} disabled={chatLoading || !chatInput.trim()}
                className="px-4 rounded-lg bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-40 flex items-center gap-1.5 text-xs font-semibold shrink-0 transition-colors">
                {chatLoading ? <><Loader2 size={12} className="animate-spin" /> Working…</> : <><Send size={12} /> Send</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Generate progress log ── */}
      <ProgressLog logs={genLogs} running={generating} />

      {/* ── Hours Summary — side-by-side Manual vs AI ── */}
      {features.length > 0 && (
        <div className="grid grid-cols-2 gap-3">

          {/* Manual Development panel */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2" style={{ background: 'var(--zx-head)' }}>
              <span className="text-[11px] font-semibold text-white">Manual Development</span>
            </div>
            <div className="grid grid-cols-3 divide-x divide-gray-100">
              <div className="px-4 py-3 flex flex-col gap-1">
                <span className="text-[10px] text-gray-400">Dev Hours</span>
                <span className="text-lg font-semibold text-[#0A2150]">{fmtH(totalDevH)}</span>
              </div>
              <div className="px-4 py-3 flex flex-col gap-1">
                <span className="text-[10px] text-gray-400">QA Hours</span>
                <span className="text-lg font-semibold text-[#0A2150]">{fmtH(totalQaH)}</span>
              </div>
              <div className="px-4 py-3 flex flex-col gap-1" style={{ background: 'var(--brand-tint)' }}>
                <span className="text-[10px] text-[#014BAA] font-semibold">Total Hours</span>
                <span className="text-lg font-semibold text-[#0A2150]">{fmtH(totalH)}</span>
                <span className="text-[10px] text-gray-400">{features.length} features</span>
              </div>
            </div>
          </div>

          {/* AI-Assisted Development panel */}
          <div className="rounded-xl border border-purple-700/50 overflow-hidden" style={{ background: 'linear-gradient(135deg, #1e0a3c 0%, #2d1060 100%)' }}>
            <div className="px-4 py-2.5 border-b border-purple-800/60 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={12} className="text-purple-300" />
                <span className="text-[11px] font-semibold text-purple-100">AI-Assisted Development</span>
              </div>
              <button onClick={() => setShowModuleBreakdown(v => !v)}
                className="text-[10px] text-purple-400 hover:text-purple-200 flex items-center gap-1 transition-colors">
                {showModuleBreakdown ? 'hide' : 'by module'} ▾
              </button>
            </div>
            <div className="grid grid-cols-3 divide-x divide-purple-800/40">
              <div className="px-4 py-3 flex flex-col gap-1">
                <span className="text-[10px] text-[#A9C4F5]/70">AI Dev Hours</span>
                <span className="text-lg font-semibold text-purple-100">{fmtH(aiTotalDevH)}</span>
                <span className="text-[10px] text-green-400">↓ {fmtH(totalDevH - aiTotalDevH)} saved</span>
              </div>
              <div className="px-4 py-3 flex flex-col gap-1">
                <span className="text-[10px] text-[#A9C4F5]/70">AI QA Hours</span>
                <span className="text-lg font-semibold text-purple-100">{fmtH(aiTotalQaH)}</span>
                <span className="text-[10px] text-green-400">↓ {fmtH(totalQaH - aiTotalQaH)} saved</span>
              </div>
              <div className="px-4 py-3 flex flex-col gap-1" style={{ background: 'rgba(126,34,206,0.3)' }}>
                <span className="text-[10px] text-purple-300 font-semibold">AI Total Hours</span>
                <span className="text-lg font-semibold text-white">{fmtH(aiGrandH)}</span>
                <span className="text-[10px] text-green-400 font-semibold">↓ {fmtH(savedH)} saved ({Math.round((1 - aiGrandH / totalH) * 100)}%)</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Module-wise AI breakdown (expandable) ── */}
      {features.length > 0 && showModuleBreakdown && (
        <div className="rounded-xl border border-purple-700/50 overflow-hidden" style={{ background: '#150830' }}>
          <div className="px-4 py-2 border-b border-purple-800/50 flex items-center gap-2">
            <Zap size={11} className="text-purple-400" />
            <span className="text-[11px] font-semibold text-purple-300">Module-wise AI Factor</span>
            <span className="text-[10px] text-purple-600 ml-2">Drag sliders to adjust per-module AI time reduction</span>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-purple-800/40">
                <th className="px-4 py-2 text-left text-purple-500 font-semibold">Module</th>
                <th className="px-4 py-2 text-right text-purple-500 font-semibold">Manual h</th>
                <th className="px-4 py-2 text-center text-purple-500 font-semibold" style={{ minWidth: '160px' }}>AI Factor</th>
                <th className="px-4 py-2 text-right text-purple-300 font-semibold">AI h</th>
                <th className="px-4 py-2 text-right text-green-500 font-semibold">Saved h</th>
              </tr>
            </thead>
            <tbody>
              {moduleRows.map(r => (
                <tr key={r.mod} className="border-b border-purple-900/30 hover:bg-purple-900/20 transition-colors">
                  <td className="px-4 py-2.5 text-purple-200 font-medium">{r.mod}</td>
                  <td className="px-4 py-2.5 text-right text-purple-400">{fmtH(r.manualH)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <input type="range" min={10} max={90} step={5}
                        value={Math.round(getModuleFactor(r.mod) * 100)}
                        onChange={e => setModuleFactors(prev => ({ ...prev, [r.mod]: Number(e.target.value) / 100 }))}
                        className="flex-1 accent-purple-500" />
                      <span className="text-[11px] text-purple-300 font-mono w-8 text-right">{Math.round(getModuleFactor(r.mod) * 100)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold text-white">{fmtH(r.aiTotalH)}</td>
                  <td className="px-4 py-2.5 text-right font-semibold text-green-400">{fmtH(r.manualH - r.aiTotalH)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-purple-700/60" style={{ background: 'rgba(88,28,135,0.3)' }}>
                <td className="px-4 py-2.5 font-semibold text-purple-200">Total</td>
                <td className="px-4 py-2.5 text-right font-semibold text-purple-300">{fmtH(totalH)}</td>
                <td />
                <td className="px-4 py-2.5 text-right font-semibold text-white">{fmtH(aiGrandH)}</td>
                <td className="px-4 py-2.5 text-right font-semibold text-green-400">{fmtH(savedH)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* ── Feature tree ── */}
      {features.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-12 text-center text-gray-400 text-sm">
          No features yet. Click <strong>"Add Feature"</strong> or use <strong>"Analyse &amp; Generate Features"</strong> if a document is attached.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 overflow-hidden">
          {/* Column header */}
          <div className="grid text-xs font-semibold text-white" style={{ background: 'var(--zx-head)', gridTemplateColumns: '1fr 108px 88px 108px 88px 70px 66px 62px 76px 36px' }}>
            <div className="px-4 py-3 border-r border-white/10">Feature</div>
            <div className="px-2 py-3 text-center border-r border-white/10">Data Model</div>
            <div className="px-2 py-3 text-center border-r border-white/10">API</div>
            <div className="px-2 py-3 text-center border-r border-white/10">Biz Rules</div>
            <div className="px-2 py-3 text-center border-r border-white/20">UI</div>
            <div className="px-2 py-3 text-center border-r border-white/20">Fixed h</div>
            <div className="px-3 py-3 text-right border-r border-white/10" style={{ color: '#8FE3B9' }}>Dev h</div>
            <div className="px-3 py-3 text-right border-r border-white/10">QA h</div>
            <div className="px-3 py-3 text-right border-r border-white/10">Total h</div>
            <div className="py-3" />
          </div>

          {/* Group features by module → sub-module */}
          {(() => {
            type SubGroup = { sub: string; feats: EstimationFeature[] }
            type ModGroup = { mod: string; subs: SubGroup[] }
            const moduleMap = new Map<string, Map<string, EstimationFeature[]>>()
            for (const f of features) {
              const mod = f.module || 'General'
              const sub = f.sub_module || ''
              if (!moduleMap.has(mod)) moduleMap.set(mod, new Map())
              const sm = moduleMap.get(mod)!
              if (!sm.has(sub)) sm.set(sub, [])
              sm.get(sub)!.push(f)
            }
            const groups: ModGroup[] = [...moduleMap.entries()].map(([mod, sm]) => ({
              mod,
              subs: [...sm.entries()].map(([sub, feats]) => ({ sub, feats })),
            }))

            return groups.map(({ mod, subs }) => {
              const modFeats = subs.flatMap(s => s.feats)
              const modTotalH = modFeats.reduce((s, f) => s + f.total_hours, 0)
              const isModCollapsed = collapsedModules.has(mod)

              return (
                <div key={mod} className="border-b border-gray-200 last:border-b-0">
                  {/* Module header row */}
                  <div className="flex items-center gap-2 px-4 py-2.5 bg-[#EEF3FB] border-b border-blue-100 cursor-pointer select-none group"
                    onClick={() => setCollapsedModules(prev => { const s = new Set(prev); s.has(mod) ? s.delete(mod) : s.add(mod); return s })}>
                    <span className="text-sm text-[#014BAA] transition-transform leading-none" style={{ display: 'inline-block', transform: isModCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>▾</span>
                    <span className="text-sm font-semibold text-[#0A2150]">{mod}</span>
                    <span className="text-xs text-gray-400 ml-1">{modFeats.length} features</span>
                    <span className="ml-auto text-xs font-semibold text-[#014BAA]">{fmtH(modTotalH)} total</span>
                    {!isModCollapsed && (
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); setAddingInModule(mod); setNewSubModuleInput('') }}
                        className="opacity-0 group-hover:opacity-100 text-xs text-[#014BAA] hover:text-[#0A2150] flex items-center gap-0.5 transition-opacity ml-2"
                      >
                        <Plus size={11} /> sub-module
                      </button>
                    )}
                  </div>

                  {!isModCollapsed && (
                    <div>
                      {subs.map(({ sub, feats: subFeats }) => {
                        const subKey = `${mod}::${sub}`
                        const isSubCollapsed = collapsedSubModules.has(subKey)
                        const subTotalH = subFeats.reduce((s, f) => s + f.total_hours, 0)

                        return (
                          <div key={subKey} className="border-b border-gray-100 last:border-b-0">
                            {/* Sub-module header (only show if sub is non-empty) */}
                            {sub && (
                              <div className="flex items-center gap-2 px-6 py-2 bg-gray-50 border-b border-gray-200 cursor-pointer select-none group"
                                onClick={() => setCollapsedSubModules(prev => { const s = new Set(prev); s.has(subKey) ? s.delete(subKey) : s.add(subKey); return s })}>
                                <span className="text-xs text-gray-400 transition-transform leading-none" style={{ display: 'inline-block', transform: isSubCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>▾</span>
                                <span className="text-xs font-semibold text-gray-600">{sub}</span>
                                <span className="text-xs text-gray-400 ml-1">{subFeats.length}</span>
                                <span className="ml-auto text-xs text-gray-400">{fmtH(subTotalH)} total</span>
                                <button
                                  type="button"
                                  onClick={e => { e.stopPropagation(); setAddingInSubModule({ mod, sub }); setNewFeature(''); setNewModule(mod) }}
                                  className="opacity-0 group-hover:opacity-100 text-xs text-[#1F7A56] hover:text-green-700 flex items-center gap-0.5 transition-opacity ml-2"
                                >
                                  <Plus size={11} /> feature
                                </button>
                              </div>
                            )}

                            {!isSubCollapsed && (
                              <div>
                                {subFeats.map(feat => (
                                  <div key={feat.id}
                                    className={`grid items-stretch border-b border-gray-100 hover:bg-blue-50/30 transition-colors ${saving === feat.id ? 'opacity-50' : ''}`}
                                    style={{ gridTemplateColumns: '1fr 108px 88px 108px 88px 70px 66px 62px 76px 36px' }}>
                                    <div className={`flex items-center border-r border-gray-200 py-2.5 pr-3 ${sub ? 'pl-10' : 'pl-6'}`}>
                                      <span className="text-sm font-medium text-gray-800 truncate" title={feat.feature}>{feat.feature}</span>
                                    </div>
                                    <div className="flex items-center justify-center px-2 py-2 border-r border-gray-100">
                                      <ComplexitySelect value={feat.data_model_complexity} onChange={v => handleComplexityChange(feat, 'data_model_complexity', v)} disabled={saving === feat.id} />
                                    </div>
                                    <div className="flex items-center justify-center px-2 py-2 border-r border-gray-100">
                                      <ComplexitySelect value={feat.api_complexity} onChange={v => handleComplexityChange(feat, 'api_complexity', v)} disabled={saving === feat.id} />
                                    </div>
                                    <div className="flex items-center justify-center px-2 py-2 border-r border-gray-100">
                                      <ComplexitySelect value={feat.business_rules_complexity} onChange={v => handleComplexityChange(feat, 'business_rules_complexity', v)} disabled={saving === feat.id} />
                                    </div>
                                    <div className="flex items-center justify-center px-2 py-2 border-r border-gray-200">
                                      <ComplexitySelect value={feat.ui_complexity} onChange={v => handleComplexityChange(feat, 'ui_complexity', v)} disabled={saving === feat.id} />
                                    </div>
                                    <div className="flex items-center justify-center px-2 py-2 border-r border-gray-200">
                                      <input type="number" min={0} step={0.5} value={feat.fixed_hours}
                                        onChange={e => handleFixedHoursChange(feat, Number(e.target.value))}
                                        className="w-14 border border-gray-200 rounded px-1.5 py-1 text-xs text-center focus:outline-none focus:border-[#014BAA]" />
                                    </div>
                                    <div className="flex items-center justify-end px-3 py-2.5 border-r border-gray-100">
                                      <span className="text-sm font-semibold text-[#014BAA]">{fmtH(feat.total_dev_hours)}</span>
                                    </div>
                                    <div className="flex items-center justify-end px-3 py-2.5 border-r border-gray-100">
                                      <span className="text-sm text-gray-400">{fmtH(feat.total_qa_hours)}</span>
                                    </div>
                                    <div className="flex items-center justify-end px-3 py-2.5 border-r border-gray-200">
                                      <span className="text-sm font-semibold text-gray-800">{fmtH(feat.total_hours)}</span>
                                    </div>
                                    <div className="flex items-center justify-center py-2.5">
                                      <button onClick={() => handleDelete(feat.id)} disabled={deletingId === feat.id}
                                        className="text-gray-300 hover:text-red-500 transition-colors disabled:opacity-50">
                                        {deletingId === feat.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                                      </button>
                                    </div>
                                  </div>
                                ))}

                                {/* Inline add feature inside this sub-module */}
                                {addingInSubModule?.mod === mod && addingInSubModule?.sub === sub && (
                                  <div className={`flex items-center gap-2 px-3 py-1.5 bg-green-50 border-b border-green-100 ${sub ? 'pl-10' : 'pl-6'}`}>
                                    <input autoFocus type="text" value={newFeature} onChange={e => setNewFeature(e.target.value)}
                                      placeholder="Feature name…"
                                      onKeyDown={e => { if (e.key === 'Enter') { handleAddFeatureInContext(mod, sub) } if (e.key === 'Escape') setAddingInSubModule(null) }}
                                      className="flex-1 border border-green-300 rounded px-2 py-1 text-xs focus:outline-none" />
                                    <button onClick={() => handleAddFeatureInContext(mod, sub)} className="text-green-600 hover:text-green-800"><CheckCircle size={13} /></button>
                                    <button onClick={() => { setAddingInSubModule(null); setNewFeature('') }} className="text-gray-400 hover:text-gray-600"><X size={13} /></button>
                                  </div>
                                )}

                                {/* Add feature button (shown when no addingInSubModule active for this group) */}
                                {!(addingInSubModule?.mod === mod && addingInSubModule?.sub === sub) && (
                                  <button type="button"
                                    onClick={() => { setAddingInSubModule({ mod, sub }); setNewFeature(''); setNewModule(mod) }}
                                    className={`w-full text-left text-xs text-gray-400 hover:text-[#1F7A56] hover:bg-green-50 px-4 py-1.5 transition-colors ${sub ? 'pl-10' : 'pl-6'}`}>
                                    + add feature
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}

                      {/* Inline add sub-module row */}
                      {addingInModule === mod && (
                        <div className="flex items-center gap-2 px-6 py-1.5 bg-blue-50 border-b border-blue-100">
                          <input autoFocus type="text" value={newSubModuleInput} onChange={e => setNewSubModuleInput(e.target.value)}
                            placeholder="New sub-module name…"
                            onKeyDown={e => {
                              if (e.key === 'Enter' && newSubModuleInput.trim()) {
                                setAddingInModule(null)
                                setAddingInSubModule({ mod, sub: newSubModuleInput.trim() })
                                setNewFeature('')
                              }
                              if (e.key === 'Escape') setAddingInModule(null)
                            }}
                            className="flex-1 border border-blue-300 rounded px-2 py-1 text-xs focus:outline-none" />
                          <button onClick={() => {
                            if (newSubModuleInput.trim()) {
                              setAddingInModule(null)
                              setAddingInSubModule({ mod, sub: newSubModuleInput.trim() })
                              setNewFeature('')
                            }
                          }} className="text-blue-600 hover:text-blue-800"><CheckCircle size={13} /></button>
                          <button onClick={() => setAddingInModule(null)} className="text-gray-400 hover:text-gray-600"><X size={13} /></button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })
          })()}

          {/* Add new module row */}
          {addingRow && (
            <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 border-t border-blue-100">
              <input autoFocus type="text" value={newModule} onChange={e => setNewModule(e.target.value)}
                placeholder="Module name…"
                onKeyDown={e => { if (e.key === 'Enter' && newModule.trim()) { setAddingRow(false); setAddingInSubModule({ mod: newModule.trim(), sub: '' }); setNewFeature('') } if (e.key === 'Escape') { setAddingRow(false); setNewModule('') } }}
                className="flex-1 border border-blue-300 rounded px-2 py-1 text-xs focus:outline-none" />
              <button onClick={() => { if (newModule.trim()) { setAddingRow(false); setAddingInSubModule({ mod: newModule.trim(), sub: '' }); setNewFeature('') } }} className="text-blue-600 hover:text-blue-800"><CheckCircle size={13} /></button>
              <button onClick={() => { setAddingRow(false); setNewModule('') }} className="text-gray-400 hover:text-gray-600"><X size={13} /></button>
            </div>
          )}

          {/* Grand total footer */}
          <div className="grid items-stretch text-sm font-semibold text-white" style={{ background: 'var(--zx-head)', gridTemplateColumns: '1fr 108px 88px 108px 88px 70px 66px 62px 76px 36px' }}>
            <div className="px-4 py-2.5 text-xs border-r border-white/10">Total</div>
            <div className="border-r border-white/10" />
            <div className="border-r border-white/10" />
            <div className="border-r border-white/10" />
            <div className="border-r border-white/20" />
            <div className="border-r border-white/20" />
            <div className="px-3 py-2.5 text-right border-r border-white/10" style={{ color: '#8FE3B9' }}>{fmtH(totalDevH)}</div>
            <div className="px-3 py-2.5 text-right text-gray-300 border-r border-white/10">{fmtH(totalQaH)}</div>
            <div className="px-3 py-2.5 text-right border-r border-white/10">{fmtH(totalH)}</div>
            <div />
          </div>
        </div>
      )}

      {/* Generation Wizard */}
      {showWizard && (
        <GenerationWizardModal
          onClose={() => setShowWizard(false)}
          onGenerate={(platform, techStack, model, temperature, seed) => {
            setShowWizard(false)
            onGenerate(platform, techStack, model, temperature, seed)
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Resources Tab
// ---------------------------------------------------------------------------

function ResourcesTab({
  project,
  onProjectUpdate,
}: {
  project: EstimationProject
  onProjectUpdate: (p: EstimationProject) => void
}) {
  const [saving, setSaving] = useState<number | null>(null)
  const [deleting, setDeleting] = useState<number | null>(null)
  const [toggling, setToggling] = useState<number | null>(null)
  const [editVals, setEditVals] = useState<Record<number, { count: string; hourly_rate: string; effort_pct: string }>>({})
  const [addingRow, setAddingRow] = useState(false)
  const [newRole, setNewRole] = useState('')
  const [newResp, setNewResp] = useState('')
  const [newCount, setNewCount] = useState('1')
  const [newEffort, setNewEffort] = useState('5')
  const [newRate, setNewRate] = useState('0')
  const [addSaving, setAddSaving] = useState(false)

  function getEdit(res: EstimationResource) {
    return editVals[res.id] ?? {
      count: String(res.count),
      hourly_rate: String(res.hourly_rate),
      effort_pct: String(Math.round(res.effort_pct * 100)),
    }
  }

  async function handleSaveResource(res: EstimationResource) {
    const ev = getEdit(res)
    setSaving(res.id)
    try {
      const { data } = await estimationProjectsApi.updateResource(project.id, res.id, {
        count: Number(ev.count),
        hourly_rate: Number(ev.hourly_rate),
        effort_pct: Number(ev.effort_pct) / 100,
      })
      onProjectUpdate(data)
      setEditVals(prev => { const n = { ...prev }; delete n[res.id]; return n })
    } catch (err) { console.error(err) }
    finally { setSaving(null) }
  }

  async function handleToggle(res: EstimationResource) {
    setToggling(res.id)
    try {
      const { data } = await estimationProjectsApi.updateResource(project.id, res.id, {
        is_active: !res.is_active,
      })
      onProjectUpdate(data)
    } catch (err) { console.error(err) }
    finally { setToggling(null) }
  }

  async function handleDelete(res: EstimationResource) {
    setDeleting(res.id)
    try {
      const { data } = await estimationProjectsApi.deleteResource(project.id, res.id)
      onProjectUpdate(data)
    } catch (err) { console.error(err) }
    finally { setDeleting(null) }
  }

  async function handleAddResource() {
    if (!newRole.trim()) return
    setAddSaving(true)
    try {
      const { data } = await estimationProjectsApi.addResource(project.id, {
        role: newRole.trim(),
        responsibility: newResp.trim() || null,
        count: Number(newCount) || 1,
        effort_pct: (Number(newEffort) || 5) / 100,
        hourly_rate: Number(newRate) || 0,
      })
      onProjectUpdate(data)
      setNewRole(''); setNewResp(''); setNewCount('1'); setNewEffort('5'); setNewRate('0')
      setAddingRow(false)
    } catch (err) { console.error(err) }
    finally { setAddSaving(false) }
  }

  const activeResources   = project.resources.filter(r => r.is_active !== false)
  const internalCostTotal = activeResources.reduce((s, r) => s + r.total_cost, 0)

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--zx-head)' }} className="text-white text-xs">
              <th className="px-4 py-3 text-left font-semibold">Role</th>
              <th className="px-4 py-3 text-left font-semibold">Responsibility</th>
              <th className="px-4 py-3 text-center font-semibold w-16">Count</th>
              <th className="px-4 py-3 text-center font-semibold w-20">% Effort</th>
              <th className="px-4 py-3 text-right font-semibold w-24" style={{ color: '#8FE3B9' }}>Hours</th>
              <th className="px-4 py-3 text-right font-semibold w-28">Rate (₹/hr)</th>
              <th className="px-4 py-3 text-right font-semibold w-28">Total Cost (₹)</th>
              <th className="px-4 py-3 text-center font-semibold w-16">Active</th>
              <th className="px-4 py-3 w-16"></th>
            </tr>
          </thead>
          <tbody>
            {project.resources.map((res) => {
              const ev = getEdit(res)
              const isActive = res.is_active !== false
              const isDirty = ev.count !== String(res.count)
                || ev.hourly_rate !== String(res.hourly_rate)
                || ev.effort_pct !== String(Math.round(res.effort_pct * 100))
              return (
                <tr key={res.id}
                  className={`border-b border-gray-100 transition-colors ${isActive ? 'hover:bg-blue-50/20' : 'bg-gray-50/60 opacity-60'}`}>
                  <td className="px-4 py-2.5 font-semibold text-gray-800">{res.role}</td>
                  <td className="px-4 py-2.5 text-gray-500 max-w-[200px] truncate text-xs">{res.responsibility || '—'}</td>
                  <td className="px-4 py-2.5 text-center">
                    <input type="number" min={0} max={20} value={ev.count} disabled={!isActive}
                      onChange={e => setEditVals(prev => ({ ...prev, [res.id]: { ...getEdit(res), count: e.target.value } }))}
                      className="w-12 border border-gray-300 rounded px-1 py-0.5 text-center text-xs focus:outline-none focus:border-[#014BAA] disabled:opacity-40 disabled:bg-gray-100" />
                  </td>
                  <td className="px-4 py-2.5 text-center">
                    <div className="flex items-center justify-center gap-0.5">
                      <input type="number" min={0} max={100} step={1} value={ev.effort_pct} disabled={!isActive}
                        onChange={e => setEditVals(prev => ({ ...prev, [res.id]: { ...getEdit(res), effort_pct: e.target.value } }))}
                        className="w-12 border border-gray-300 rounded px-1 py-0.5 text-center text-xs focus:outline-none focus:border-[#014BAA] disabled:opacity-40 disabled:bg-gray-100" />
                      <span className="text-xs text-gray-400">%</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-semibold text-[#014BAA] text-sm">{fmtH(res.effort_hours)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <input type="number" min={0} step={100} value={ev.hourly_rate} disabled={!isActive}
                      onChange={e => setEditVals(prev => ({ ...prev, [res.id]: { ...getEdit(res), hourly_rate: e.target.value } }))}
                      className="w-24 border border-gray-300 rounded px-1.5 py-0.5 text-right text-xs focus:outline-none focus:border-[#014BAA] disabled:opacity-40 disabled:bg-gray-100" />
                  </td>
                  <td className={`px-4 py-2.5 text-right font-semibold text-sm ${isActive ? 'text-gray-800' : 'text-gray-400 line-through'}`}>
                    ₹{fmt(res.total_cost)}
                  </td>
                  {/* Active toggle */}
                  <td className="px-4 py-2.5 text-center">
                    <button
                      onClick={() => handleToggle(res)}
                      disabled={toggling === res.id}
                      title={isActive ? 'Disable this resource' : 'Enable this resource'}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${isActive ? 'bg-[#014BAA]' : 'bg-gray-300'}`}
                    >
                      {toggling === res.id
                        ? <Loader2 size={10} className="animate-spin mx-auto text-white" />
                        : <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${isActive ? 'translate-x-4' : 'translate-x-1'}`} />
                      }
                    </button>
                  </td>
                  {/* Actions */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {isDirty && (
                        <button onClick={() => handleSaveResource(res)} disabled={saving === res.id || !isActive}
                          className="text-[#014BAA] hover:text-[#0A2150] text-xs font-medium disabled:opacity-40">
                          {saving === res.id ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                        </button>
                      )}
                      <button onClick={() => handleDelete(res)} disabled={deleting === res.id}
                        className="text-gray-300 hover:text-red-500 transition-colors disabled:opacity-40">
                        {deleting === res.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={13} />}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}

            {/* Inline add-resource row */}
            {addingRow && (
              <tr className="border-b border-blue-100 bg-blue-50">
                <td className="px-3 py-2">
                  <input autoFocus type="text" value={newRole} onChange={e => setNewRole(e.target.value)}
                    placeholder="Role name *"
                    onKeyDown={e => { if (e.key === 'Enter') handleAddResource(); if (e.key === 'Escape') setAddingRow(false) }}
                    className="w-full border border-blue-300 rounded px-2 py-1 text-xs focus:outline-none" />
                </td>
                <td className="px-3 py-2">
                  <input type="text" value={newResp} onChange={e => setNewResp(e.target.value)}
                    placeholder="Responsibility"
                    className="w-full border border-blue-300 rounded px-2 py-1 text-xs focus:outline-none" />
                </td>
                <td className="px-3 py-2 text-center">
                  <input type="number" min={1} max={20} value={newCount} onChange={e => setNewCount(e.target.value)}
                    className="w-12 border border-blue-300 rounded px-1 py-1 text-center text-xs focus:outline-none" />
                </td>
                <td className="px-3 py-2 text-center">
                  <div className="flex items-center justify-center gap-0.5">
                    <input type="number" min={0} max={100} value={newEffort} onChange={e => setNewEffort(e.target.value)}
                      className="w-12 border border-blue-300 rounded px-1 py-1 text-center text-xs focus:outline-none" />
                    <span className="text-xs text-gray-400">%</span>
                  </div>
                </td>
                <td />
                <td className="px-3 py-2">
                  <input type="number" min={0} step={100} value={newRate} onChange={e => setNewRate(e.target.value)}
                    className="w-24 border border-blue-300 rounded px-1.5 py-1 text-right text-xs focus:outline-none" />
                </td>
                <td /><td />
                <td className="px-3 py-2">
                  <div className="flex gap-1.5">
                    <button onClick={handleAddResource} disabled={addSaving || !newRole.trim()}
                      className="text-green-600 hover:text-green-800 disabled:opacity-40">
                      {addSaving ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                    </button>
                    <button onClick={() => { setAddingRow(false); setNewRole('') }} className="text-gray-400 hover:text-gray-600">
                      <X size={13} />
                    </button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
          {project.resources.length > 0 && (
            <tfoot>
              <tr style={{ background: 'var(--zx-head)' }} className="text-white">
                <td colSpan={6} className="px-4 py-2.5 text-xs font-semibold">
                  TOTAL INTERNAL COST
                  {project.resources.some(r => r.is_active === false) && (
                    <span className="ml-2 text-gray-400 font-normal">(active resources only)</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right font-semibold text-sm">₹{fmt(internalCostTotal)}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Add resource button */}
      {!addingRow && (
        <button
          onClick={() => setAddingRow(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-sm text-[#014BAA] border border-dashed border-[#014BAA] rounded-lg hover:bg-blue-50 transition-colors font-medium"
        >
          <Plus size={14} /> Add Resource
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cost Summary Tab
// ---------------------------------------------------------------------------

function CostSummaryTab({
  project,
  aiToolsFactor,
  moduleFactors,
}: {
  project: EstimationProject
  aiToolsFactor: number
  moduleFactors: Record<string, number>
}) {
  function getModFactor(mod: string | null) {
    return moduleFactors[mod || 'General'] ?? aiToolsFactor
  }
  const summary = project.summary
  const pmH        = summary?.pm_hours       ?? project.total_dev_hours * project.pm_pct
  const archH      = summary?.design_arch_hours ?? project.total_dev_hours * project.design_arch_pct
  const uiuxH      = summary?.spec_uiux_hours   ?? project.total_dev_hours * project.spec_uiux_pct
  const bufH       = summary?.dev_buffer_hours  ?? project.total_dev_hours * project.dev_buffer_pct
  const grandDev   = summary?.grand_total_dev   ?? project.grand_total_hours - project.total_qa_hours

  // Duration estimate (using total dev team size from resources)
  const teamSize = Math.max(1, project.resources.filter(r =>
    r.role.toLowerCase().includes('developer') || r.role.toLowerCase().includes('backend') || r.role.toLowerCase().includes('frontend')
  ).reduce((s, r) => s + r.count, 0))
  const durationWeeks = project.grand_total_hours > 0
    ? Math.ceil(project.grand_total_hours / 8 / 5 / teamSize)
    : 0

  const suggestedBid = project.total_project_cost * 1.05

  function BigCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
    return (
      <div className={`rounded-xl p-5 flex flex-col gap-1 ${accent ? 'bg-[var(--zx-head)] text-white' : 'bg-white border border-gray-200'}`}>
        <span className={`text-xs font-medium ${accent ? 'text-blue-200' : 'text-gray-500'}`}>{label}</span>
        <span className={`text-2xl font-semibold ${accent ? 'text-white' : 'text-[#0A2150]'}`}>{value}</span>
      </div>
    )
  }

  function Row({ label, value, bold, accent }: { label: string; value: string; bold?: boolean; accent?: boolean }) {
    return (
      <div className={`flex justify-between items-center py-2 border-b border-gray-100 last:border-0 ${bold ? 'font-semibold' : ''}`}>
        <span className={`text-sm ${accent ? 'text-[#014BAA]' : 'text-gray-700'}`}>{label}</span>
        <span className={`text-sm ${accent ? 'text-[#014BAA] font-semibold' : bold ? 'text-[#0A2150]' : 'text-gray-800'}`}>{value}</span>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Top metric cards */}
      <div className="grid grid-cols-4 gap-3">
        <BigCard label="Total Dev Hours" value={fmtH(project.total_dev_hours)} />
        <BigCard label="Total QA Hours" value={fmtH(project.total_qa_hours)} />
        <BigCard label="Grand Total Hours" value={fmtH(project.grand_total_hours)} />
        <BigCard label="Estimated Duration" value={`${durationWeeks}w`} />
      </div>

      <div className="grid grid-cols-2 gap-5">
        {/* Left: overheads + resources */}
        <div className="space-y-4">
          {/* Overhead breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-[#0A2150] mb-3">Project Overheads (on {fmtH(project.total_dev_hours)} dev hours)</h3>
            <Row label="Feature Dev Hours" value={fmtH(project.total_dev_hours)} />
            <Row label={`PM (${pct(project.pm_pct)})`} value={fmtH(pmH)} />
            <Row label={`Design & Arch (${pct(project.design_arch_pct)})`} value={fmtH(archH)} />
            <Row label={`Spec / UI-UX (${pct(project.spec_uiux_pct)})`} value={fmtH(uiuxH)} />
            <Row label={`Dev Buffer (${pct(project.dev_buffer_pct)})`} value={fmtH(bufH)} />
            <Row label="Grand Total Dev Hours" value={fmtH(grandDev)} bold />
            <Row label="Total QA Hours" value={fmtH(project.total_qa_hours)} />
            <Row label="Grand Total Hours" value={fmtH(project.grand_total_hours)} bold accent />
          </div>

          {/* Resource cost breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-[#0A2150] mb-3">Resource Cost Breakdown</h3>
            {project.resources.map((res) => (
              <Row
                key={res.id}
                label={`${res.role} (${res.count}×, ₹${fmt(res.hourly_rate)}/hr, ${fmtH(res.effort_hours)})`}
                value={`₹${fmt(res.total_cost)}`}
              />
            ))}
            <Row label="Internal Cost Total" value={`₹${fmt(project.internal_cost)}`} bold accent />
          </div>
        </div>

        {/* Right: cost summary */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-[#0A2150] mb-3">Cost Summary</h3>
            <Row label="Internal Cost" value={`₹${fmt(project.internal_cost)}`} />
            <Row label={`Margin (${pct(project.margin_pct)})`} value={`₹${fmt(project.margin_amount)}`} />
            <Row label="Infrastructure Cost" value={`₹${fmt(project.infra_cost)}`} />
            <Row label="Total Project Cost" value={`₹${fmt(project.total_project_cost)}`} bold accent />
          </div>

          {/* Highlighted cards */}
          <div className="rounded-xl p-5 flex flex-col gap-1" style={{ background: 'var(--zx-head)' }}>
            <span className="text-xs font-medium text-blue-200">Total Project Cost</span>
            <span className="text-3xl font-semibold text-white">₹{fmt(project.total_project_cost)}</span>
            <span className="text-xs text-blue-300 mt-1">Including {pct(project.margin_pct)} margin + ₹{fmt(project.infra_cost)} infra</span>
          </div>

          <div className="rounded-xl p-5 flex flex-col gap-1" style={{ background: '#1F7A56' }}>
            <span className="text-xs font-medium text-green-100">Suggested Bid Value</span>
            <span className="text-3xl font-semibold text-white">₹{fmt(suggestedBid)}</span>
            <span className="text-xs text-green-100 mt-1">Total × 1.05 (5% bid premium)</span>
          </div>

          {/* AI-assisted path cost card */}
          {(() => {
            const aiDevH = project.features.reduce((s, f) => s + f.total_dev_hours * getModFactor(f.module), 0)
            const aiQaH  = aiDevH * 0.40
            const aiGrandDevH = aiDevH * (1 + project.pm_pct + project.design_arch_pct + project.spec_uiux_pct + project.dev_buffer_pct)
            const aiGrandH    = aiGrandDevH + aiQaH
            const aiRatio     = project.grand_total_hours > 0 ? aiGrandH / project.grand_total_hours : 0
            const aiCost      = project.total_project_cost * aiRatio
            const aiSaved     = project.total_project_cost - aiCost
            const avgFactor   = project.features.length > 0
              ? project.features.reduce((s, f) => s + getModFactor(f.module), 0) / project.features.length
              : aiToolsFactor
            return (
              <div className="rounded-xl p-5 flex flex-col gap-2 bg-purple-900 border border-purple-700">
                <div className="flex items-center gap-2">
                  <Zap size={14} className="text-yellow-400" />
                  <span className="text-xs font-semibold text-purple-200">AI-Assisted Development Cost</span>
                </div>
                <span className="text-3xl font-semibold text-white">₹{fmt(aiCost)}</span>
                <div className="text-xs text-purple-300 space-y-0.5">
                  <div className="flex justify-between">
                    <span>AI Total Hours</span><span className="font-semibold text-purple-100">{fmtH(aiGrandH)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Hours Saved</span><span className="font-semibold text-green-400">{fmtH(project.grand_total_hours - aiGrandH)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cost Saved</span><span className="font-semibold text-green-400">₹{fmt(aiSaved)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Avg AI factor</span><span className="font-semibold text-purple-100">{Math.round(avgFactor * 100)}% of manual</span>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Settings summary pills */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <h3 className="text-sm font-semibold text-[#0A2150] mb-3">Active Buffers</h3>
            <div className="flex flex-wrap gap-2">
              {[
                { label: 'Complexity', val: project.complexity_pct },
                { label: 'Unit Testing', val: project.unit_testing_pct },
                { label: 'Rework', val: project.rework_pct },
              ].map(({ label, val }) => (
                <span key={label} className="bg-blue-50 text-[#014BAA] text-xs px-2 py-1 rounded-full border border-blue-200">
                  {label}: {pct(val)}
                </span>
              ))}
              {[
                { label: 'PM', val: project.pm_pct },
                { label: 'Arch', val: project.design_arch_pct },
                { label: 'UI-UX', val: project.spec_uiux_pct },
                { label: 'Dev Buffer', val: project.dev_buffer_pct },
              ].map(({ label, val }) => (
                <span key={label} className="bg-gray-50 text-gray-600 text-xs px-2 py-1 rounded-full border border-gray-200">
                  {label}: {pct(val)}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function ProjectEstimationPage() {
  const [projects, setProjects] = useState<EstimationProjectListItem[]>([])
  const [activeProject, setActiveProject] = useState<EstimationProject | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('features')
  const [showNewModal, setShowNewModal] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadingProject, setLoadingProject] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genLogs, setGenLogs] = useState<ProgressMessage[]>([])
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showDocPicker, setShowDocPicker] = useState(false)
  const [aiToolsFactor, setAiToolsFactor] = useState(0.35) // 65% faster with AI tools
  const [moduleFactors, setModuleFactors] = useState<Record<string, number>>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset module factors when global AI factor changes
  useEffect(() => {
    setModuleFactors({})
  }, [aiToolsFactor])

  // Load project list and documents on mount
  useEffect(() => {
    loadProjects()
    loadDocuments()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  async function loadProjects() {
    setLoadingProjects(true)
    try {
      const { data } = await estimationProjectsApi.list()
      setProjects(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingProjects(false)
    }
  }

  async function loadDocuments() {
    try {
      const { data } = await documentsApi.list()
      setDocuments(data.filter(d => d.status === 'ANALYZED'))
    } catch (err) {
      console.error(err)
    }
  }

  async function handleSelectProject(id: number) {
    setLoadingProject(true)
    setError(null)
    stopPoll()
    try {
      const { data } = await estimationProjectsApi.get(id)
      setActiveProject(data)
      setActiveTab('features')
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingProject(false)
    }
  }

  async function handleCreateProject(name: string, documentId: number | null) {
    const { data } = await estimationProjectsApi.create({ name, document_id: documentId })
    setProjects(prev => [{ ...data }, ...prev])
    setActiveProject(data)
    setActiveTab('features')
  }

  async function handleDeleteProject(id: number) {
    if (!confirm('Delete this estimation project?')) return
    try {
      await estimationProjectsApi.delete(id)
      setProjects(prev => prev.filter(p => p.id !== id))
      if (activeProject?.id === id) setActiveProject(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Delete failed')
    }
  }

  async function handleSaveSettings(updates: Record<string, number>) {
    if (!activeProject) return
    setSavingSettings(true)
    try {
      const { data } = await estimationProjectsApi.update(activeProject.id, updates)
      // Also recalculate
      const { data: recalcData } = await estimationProjectsApi.recalculate(activeProject.id)
      setActiveProject(recalcData)
      setProjects(prev => prev.map(p => p.id === recalcData.id
        ? { ...p, total_project_cost: recalcData.total_project_cost, grand_total_hours: recalcData.grand_total_hours }
        : p
      ))
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save settings')
    } finally {
      setSavingSettings(false)
    }
  }

  function handleProjectUpdate(updatedProject: EstimationProject) {
    setActiveProject(updatedProject)
    setProjects(prev => prev.map(p => p.id === updatedProject.id
      ? { ...p, total_project_cost: updatedProject.total_project_cost, grand_total_hours: updatedProject.grand_total_hours }
      : p
    ))
  }

  function stopPoll() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  function startPoll(projectId: number) {
    stopPoll()
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await estimationProjectsApi.getProgress(projectId)
        setGenLogs(data.messages)
        // Check if done (last message is success or error)
        const last = data.messages[data.messages.length - 1]
        if (last && (last.level === 'success' || last.level === 'error') && last.message.toLowerCase().includes('complete')) {
          stopPoll()
          setGenerating(false)
          // Reload project to get fresh features
          const { data: refreshed } = await estimationProjectsApi.get(projectId)
          setActiveProject(refreshed)
          setProjects(prev => prev.map(p => p.id === refreshed.id
            ? { ...p, total_project_cost: refreshed.total_project_cost, grand_total_hours: refreshed.grand_total_hours }
            : p
          ))
        }
      } catch {
        // ignore poll errors
      }
    }, 1500)
  }

  async function handleGenerate(
    platform: Platform,
    techStack: Record<string, string[]>,
    model: string,
    temperature: number,
    seed: number | undefined,
  ) {
    if (!activeProject) return
    setGenerating(true)
    setGenLogs([])
    setError(null)
    try {
      await estimationProjectsApi.generate(activeProject.id, {
        platform,
        tech_stack: techStack,
        model: model || undefined,
        temperature,
        seed,
      })
      startPoll(activeProject.id)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start generation')
      setGenerating(false)
    }
  }

  async function handleAttachDocument(docId: number, filename: string) {
    if (!activeProject) return
    setShowDocPicker(false)
    try {
      const { data } = await estimationProjectsApi.update(activeProject.id, { document_id: docId })
      handleProjectUpdate(data)
      loadDocuments()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to attach document')
    }
  }

  async function handleDetachDocument() {
    if (!activeProject?.document_id) return
    try {
      await documentsApi.delete(activeProject.document_id)
    } catch {
      // ignore if already deleted
    }
    try {
      const { data } = await estimationProjectsApi.update(activeProject.id, { document_id: null })
      handleProjectUpdate(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to detach document')
    }
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: 'features',  label: 'Features' },
    { id: 'resources', label: 'Resources' },
    { id: 'summary',   label: 'Cost Summary' },
  ]

  return (
    <div className="flex h-full gap-3 p-3" style={{ minHeight: 'calc(100vh - 80px)' }}>
      {/* ------------------------------------------------------------------ */}
      {/* LEFT SIDEBAR                                                        */}
      {/* ------------------------------------------------------------------ */}
      <aside className="zx-subrail w-64 shrink-0 flex flex-col">
        {/* Header */}
        <div className="px-4 py-4 border-b border-gray-200" style={{ background: 'linear-gradient(135deg, var(--brand-tint) 0%, var(--panel-2) 100%)' }}>
          <h1 className="text-base font-semibold" style={{ fontFamily: 'var(--font-heading)', color: 'var(--ink)' }}>Project estimations</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--ink-3)' }}>Effort, sprints and cost from a requirements document</p>
        </div>

        {/* New Project button */}
        <div className="p-3 border-b border-gray-200">
          <button
            onClick={() => { setShowNewModal(true); loadDocuments() }}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-[#014BAA] text-white text-xs rounded-lg font-medium hover:bg-[#013D8C] transition-colors"
          >
            <Plus size={13} /> New Project
          </button>
        </div>

        {/* Project list */}
        <div className="flex-1 overflow-y-auto py-2">
          {loadingProjects ? (
            <div className="flex items-center justify-center py-8 text-gray-400">
              <Loader2 size={16} className="animate-spin mr-2" /> Loading…
            </div>
          ) : projects.length === 0 ? (
            <div className="px-4 py-6 text-center text-xs text-gray-400">
              No projects yet. Create your first one!
            </div>
          ) : (
            projects.map((p) => (
              <div
                key={p.id}
                onClick={() => handleSelectProject(p.id)}
                className={`mx-2 mb-1 rounded-lg px-3 py-2.5 cursor-pointer group transition-colors ${
                  activeProject?.id === p.id
                    ? 'bg-[#014BAA] text-white'
                    : 'hover:bg-gray-200 text-gray-700'
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs font-semibold truncate ${activeProject?.id === p.id ? 'text-white' : 'text-gray-800'}`}>
                      {p.name}
                    </p>
                    <p className={`text-[10px] mt-0.5 ${activeProject?.id === p.id ? 'text-blue-100' : 'text-gray-500'}`}>
                      {p.total_project_cost > 0 ? `₹${fmt(p.total_project_cost)}` : 'No estimate yet'}
                    </p>
                    <span className={`inline-block text-[10px] mt-1 px-1.5 py-0.5 rounded-full font-medium ${
                      p.status === 'finalized'
                        ? (activeProject?.id === p.id ? 'bg-green-300 text-green-900' : 'bg-green-100 text-green-700')
                        : (activeProject?.id === p.id ? 'bg-blue-300 text-blue-900' : 'bg-gray-200 text-gray-600')
                    }`}>
                      {p.status}
                    </span>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteProject(p.id) }}
                    className={`opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 ${activeProject?.id === p.id ? 'text-blue-200 hover:text-white' : 'text-gray-400 hover:text-red-500'}`}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* ------------------------------------------------------------------ */}
      {/* MAIN AREA                                                           */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 overflow-y-auto p-2" data-lenis-prevent>
        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
            <AlertTriangle size={15} />
            {error}
            <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700"><X size={14} /></button>
          </div>
        )}

        {loadingProject ? (
          <div className="flex items-center justify-center py-24 text-gray-400">
            <Loader2 size={24} className="animate-spin mr-3" /> Loading project…
          </div>
        ) : !activeProject ? (
          /* Empty state */
          <div className="zx-empty mx-auto mt-10" style={{ maxWidth: '40rem' }}>
            <div className="zx-empty-icon"><FileText size={28} strokeWidth={1.5} /></div>
            <h2>No project selected</h2>
            <p>Pick a project from the list, or start one from a requirements document (SRS or RFP). The estimate comes with modules, sprints, effort and a traceable cost.</p>
            <ol className="grid sm:grid-cols-3 gap-3 text-left mt-3 w-full" style={{ listStyle: 'none' }}>
              {[['1', 'Upload', 'A requirements document'], ['2', 'Review', 'Modules, stories and sprint plan'], ['3', 'Price', 'Rates, margin and a bid value']].map(([n, t, d]) => (
                <li key={n} className="rounded-xl p-3" style={{ background: 'var(--panel-2)', border: '1px solid var(--line)' }}>
                  <span className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--ink-3)' }}>0{n}</span>
                  <p className="font-semibold text-sm" style={{ color: 'var(--ink)' }}>{t}</p>
                  <p className="text-xs" style={{ color: 'var(--ink-3)' }}>{d}</p>
                </li>
              ))}
            </ol>
            <div className="zx-actions">
              <button onClick={() => { setShowNewModal(true); loadDocuments() }} className="zx-action primary"><Plus size={15} /> Create new project</button>
            </div>
          </div>
        ) : (
          <>
            {/* Project header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-[#0A2150]">{activeProject.name}</h2>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    activeProject.status === 'finalized' ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-600'
                  }`}>
                    {activeProject.status}
                  </span>
                  <button
                    onClick={() => { loadDocuments(); setShowDocPicker(true) }}
                    className="text-xs flex items-center gap-1 text-gray-500 hover:text-[#014BAA] transition-colors group"
                  >
                    {activeProject.document_id ? (
                      <>
                        <FileText size={11} className="text-[#014BAA]" />
                        <span className="text-[#014BAA]">Document attached</span>
                        <span className="text-gray-400 group-hover:text-[#014BAA]">(change)</span>
                      </>
                    ) : (
                      <>
                        <Paperclip size={11} />
                        <span>Attach SRS document</span>
                      </>
                    )}
                  </button>
                  {activeProject.document_id && (
                    <button
                      onClick={handleDetachDocument}
                      className="text-gray-300 hover:text-red-500 transition-colors"
                      title="Remove attached document"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  to="/proposals"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-gray-300 bg-white text-gray-600 font-medium hover:border-[#014BAA] hover:text-[#014BAA] transition-colors"
                >
                  <FileText size={12} /> Proposal Generator
                </Link>
                <button
                  onClick={() => setShowSettings(s => !s)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border font-medium transition-colors ${
                    showSettings ? 'bg-[var(--zx-head)] text-white border-[var(--zx-head)]' : 'bg-white text-gray-600 border-gray-300 hover:border-[#014BAA]'
                  }`}
                >
                  <Settings size={12} /> Settings
                </button>
                {activeProject.status === 'draft' && (
                  <button
                    onClick={async () => {
                      const { data } = await estimationProjectsApi.update(activeProject.id, { status: 'finalized' })
                      handleProjectUpdate(data)
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-[#1F7A56] text-white font-medium hover:bg-[#186446]"
                  >
                    <CheckCircle size={12} /> Finalize
                  </button>
                )}
              </div>
            </div>

            {/* Settings panel */}
            {showSettings && (
              <SettingsPanel
                project={activeProject}
                onSave={handleSaveSettings}
                saving={savingSettings}
                aiToolsFactor={aiToolsFactor}
                onAiToolsFactorChange={setAiToolsFactor}
              />
            )}

            {/* Tabs */}
            <div className="flex gap-1 mt-4 mb-4 border-b border-gray-200">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${
                    activeTab === tab.id
                      ? 'text-[#014BAA] border-b-2 border-[#014BAA] bg-white'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab.label}
                  {tab.id === 'features' && activeProject.features.length > 0 && (
                    <span className="ml-1.5 text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded-full">
                      {activeProject.features.length}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === 'features' && (
              <FeaturesTab
                project={activeProject}
                onProjectUpdate={handleProjectUpdate}
                generating={generating}
                onGenerate={handleGenerate}
                genLogs={genLogs}
                aiToolsFactor={aiToolsFactor}
                moduleFactors={moduleFactors}
                setModuleFactors={setModuleFactors}
              />
            )}
            {activeTab === 'resources' && (
              <ResourcesTab
                project={activeProject}
                onProjectUpdate={handleProjectUpdate}
              />
            )}
            {activeTab === 'summary' && (
              <CostSummaryTab project={activeProject} aiToolsFactor={aiToolsFactor} moduleFactors={moduleFactors} />
            )}
          </>
        )}
      </main>

      {/* New project modal */}
      {showNewModal && (
        <NewProjectModal
          onClose={() => setShowNewModal(false)}
          onCreate={handleCreateProject}
          documents={documents}
        />
      )}

      {/* Document picker modal (for existing projects) */}
      {showDocPicker && (
        <DocumentPickerModal
          documents={documents}
          onSelect={handleAttachDocument}
          onClose={() => setShowDocPicker(false)}
        />
      )}
    </div>
  )
}
