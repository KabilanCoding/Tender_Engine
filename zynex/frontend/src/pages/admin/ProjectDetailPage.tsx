import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Upload, Trash2, FileText, Loader2 } from 'lucide-react'
import { kbApi, Project, ProjectDocument } from '../../api/knowledgeBase'

const DOC_CATEGORIES = [
  'SRS', 'TECHNICAL_PROPOSAL', 'COMMERCIAL_PROPOSAL', 'SOW',
  'ARCHITECTURE_DOC', 'FLOW_DIAGRAMS', 'TEST_CASES', 'UAT_REPORT',
  'COMPLETION_CERT', 'LESSONS_LEARNED', 'CONTRACT', 'OTHER',
]

function formatBytes(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const id = Number(projectId)

  const [project, setProject]           = useState<Project | null>(null)
  const [documents, setDocuments]       = useState<ProjectDocument[]>([])
  const [loading, setLoading]           = useState(true)
  const [uploading, setUploading]       = useState(false)
  const [uploadError, setUploadError]   = useState('')
  const [selectedCategory, setSelectedCategory] = useState('SRS')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [pollingIds, setPollingIds]     = useState<Set<number>>(new Set())

  const loadData = async () => {
    try {
      const [projRes, docsRes] = await Promise.all([
        kbApi.listProjects(),
        kbApi.listProjectDocuments(id),
      ])
      setProject(projRes.data.find(p => p.id === id) || null)
      setDocuments(docsRes.data)
      setPollingIds(new Set(
        docsRes.data.filter(d => !d.is_processed && !d.processing_error).map(d => d.id)
      ))
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [id])

  useEffect(() => {
    if (pollingIds.size === 0) return
    const timer = setInterval(async () => {
      try {
        const res = await kbApi.listProjectDocuments(id)
        setDocuments(res.data)
        setPollingIds(new Set(
          res.data.filter(d => !d.is_processed && !d.processing_error).map(d => d.id)
        ))
      } catch { /* ignore */ }
    }, 3000)
    return () => clearInterval(timer)
  }, [pollingIds, id])

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadError('')
    try {
      const formData = new FormData()
      formData.append('doc_category', selectedCategory)
      formData.append('file', file)
      await kbApi.uploadProjectDocument(id, formData)
      fileInputRef.current!.value = ''
      await loadData()
    } catch (err: any) {
      setUploadError(err?.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (docId: number) => {
    if (!confirm('Delete this document and all its chunks?')) return
    try {
      await kbApi.deleteProjectDocument(id, docId)
      setDocuments(prev => prev.filter(d => d.id !== docId))
    } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={24} className="animate-spin text-gray-400" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5 max-w-[1200px]">

      {/* Header */}
      <div className="zx-page-head">
        <div>
          <button
            onClick={() => navigate('/knowledge-base')}
            className="zx-eyebrow-line hover:underline"
          >
            <ArrowLeft size={13} /> Knowledge Base
          </button>
          <h1 className="mt-1">
            {project?.name || `Project #${id}`}
          </h1>
          <p>{project?.description || 'Documents for this project. They are read and indexed so KB Search and tender matching can use them.'}</p>
        </div>
      </div>

      {/* Project metadata */}
      {project && (
        <div className="bg-white border border-gray-200 rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-4 shadow-sm">
          {[
            { label: 'Status', value: <span className="capitalize font-medium text-gray-800">{project.status}</span> },
            { label: 'Duration', value: project.duration_weeks ? `${project.duration_weeks} weeks` : '-' },
            { label: 'Team Size', value: project.team_size || '-' },
            { label: 'Value', value: project.total_value ? `₹${project.total_value.toLocaleString()}` : '-' },
          ].map(({ label, value }) => (
            <div key={label}>
              <div className="text-gray-400 text-xs mb-1">{label}</div>
              <div className="text-gray-800 font-medium text-sm">{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Upload panel */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
        <h2 className="text-gray-800 font-semibold mb-4 flex items-center gap-2">
          <Upload size={16} style={{ color: '#014BAA' }} /> Upload Project Document
        </h2>
        <form onSubmit={handleUpload} className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-gray-500 text-xs mb-1">Category</label>
            <select
              value={selectedCategory}
              onChange={e => setSelectedCategory(e.target.value)}
              className="border border-gray-300 text-gray-800 bg-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#014BAA]"
            >
              {DOC_CATEGORIES.map(cat => (
                <option key={cat} value={cat}>{cat.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-gray-500 text-xs mb-1">File (PDF, DOCX, TXT)</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              required
              className="block w-full text-sm text-gray-600 border border-dashed border-gray-300 rounded-xl p-1.5 hover:border-[#014BAA] transition-colors file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-[#014BAA]/10 file:text-[#014BAA] hover:file:bg-[#014BAA]/20 file:cursor-pointer cursor-pointer"
            />
          </div>
          <button
            type="submit"
            disabled={uploading}
            className="zx-action primary disabled:opacity-50"
          >
            {uploading ? <><Loader2 size={14} className="animate-spin" /> Uploading...</> : 'Upload & Ingest'}
          </button>
        </form>
        {uploadError && <p className="text-red-500 text-sm mt-2">{uploadError}</p>}
        <p className="text-gray-400 text-xs mt-2">
          After upload, the document is parsed, chunked, and embedded in the background for semantic search.
        </p>
      </div>

      {/* Document list */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-gray-800 font-semibold flex items-center gap-2">
            <FileText size={16} style={{ color: '#014BAA' }} />
            Documents ({documents.length})
          </h2>
          {pollingIds.size > 0 && (
            <span className="text-amber-600 text-xs flex items-center gap-1 animate-pulse">
              <Loader2 size={12} className="animate-spin" />
              Processing {pollingIds.size} document(s)…
            </span>
          )}
        </div>

        {documents.length === 0 ? (
          <div className="px-5 py-10 text-center text-gray-400">
            No documents yet. Upload the first one above.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs">
              <tr>
                {['Filename', 'Category', 'Size', 'Pages', 'Status', 'Uploaded', ''].map(h => (
                  <th key={h} className="px-5 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => (
                <tr key={doc.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-5 py-3 text-gray-800 font-medium truncate max-w-[200px]">
                    {doc.original_filename}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ backgroundColor: '#014BAA18', color: '#014BAA' }}
                    >
                      {doc.doc_category.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-500">{formatBytes(doc.file_size_bytes)}</td>
                  <td className="px-5 py-3 text-gray-500">{doc.page_count || '-'}</td>
                  <td className="px-5 py-3">
                    {doc.processing_error ? (
                      <span className="zx-chip is-bad" title={doc.processing_error}>Failed</span>
                    ) : doc.is_processed ? (
                      <span className="zx-chip is-ok">Indexed</span>
                    ) : (
                      <span className="zx-chip is-warn"><Loader2 size={11} className="animate-spin" /> Processing</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-gray-400 text-xs">
                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="w-8 h-8 rounded-lg grid place-items-center text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                      aria-label={`Delete ${doc.original_filename}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
