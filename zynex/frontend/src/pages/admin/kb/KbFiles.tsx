import { createPortal } from 'react-dom'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Download, Eye, FileText, Loader2, Paperclip, Trash2, Upload, X } from 'lucide-react'
import { kbApi, type KbFile } from '../../../api/knowledgeBase'
import { useAuthStore } from '../../../store/authStore'
import { apiError } from './ui'

/**
 * Documents kept for knowledge-base facts. One request loads every file of an owner type (e.g. all "profile" files), and each
 * field shows only its own: a small "Attach" chip that opens a drawer to view, download, upload or delete.
 */
interface FilesCtx { files: KbFile[] | null; reload: () => void; ownerType: string }
const Ctx = createContext<FilesCtx | null>(null)

export function KbFilesProvider({ ownerType, children }: { ownerType: string; children: React.ReactNode }) {
  const [files, setFiles] = useState<KbFile[] | null>(null)
  const reload = useCallback(() => { kbApi.listFiles(ownerType).then(r => setFiles(r.data)).catch(() => setFiles([])) }, [ownerType])
  useEffect(() => { reload() }, [reload])
  return <Ctx.Provider value={{ files, reload, ownerType }}>{children}</Ctx.Provider>
}

function useFiles(ownerKey: string) {
  const ctx = useContext(Ctx)
  const mine = useMemo(() => (ctx?.files ?? []).filter(f => f.owner_key === ownerKey), [ctx?.files, ownerKey])
  return { ...ctx!, mine }
}

export function sizeText(n?: number | null): string {
  if (!n) return ''
  return n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`
}

async function openFile(f: KbFile, inline = true) {
  const { data } = await kbApi.fileBlob(f.id, inline)
  const url = URL.createObjectURL(data)
  if (inline) window.open(url, '_blank', 'noopener')
  else { const a = document.createElement('a'); a.href = url; a.download = f.original_filename; a.click() }
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

/** The list of files of one owner with upload/view/download/delete (used inside the drawer and in tables). */
export function FileList({ ownerKey, label, compact = false }: { ownerKey: string; label: string; compact?: boolean }) {
  const { mine, reload, ownerType, files } = useFiles(ownerKey)
  const isAdmin = useAuthStore(s => s.role) === 'admin'
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function upload(list: FileList | null) {
    if (!list?.length) return
    setBusy(true); setError('')
    try {
      for (const f of Array.from(list)) await kbApi.uploadFile(ownerType, ownerKey, f)
      reload()
    } catch (e) { setError(apiError(e, 'Could not upload the file.')) }
    finally { setBusy(false); if (input.current) input.current.value = '' }
  }

  async function remove(f: KbFile) {
    if (!window.confirm(`Delete ${f.original_filename}?`)) return
    await kbApi.deleteFile(f.id); reload()
  }

  if (files === null) return <span className="kb-meta">Loading…</span>
  return (
    <div className={`kb-files ${compact ? 'is-compact' : ''}`}>
      {mine.length === 0 && <p className="kb-meta">No document attached for {label}.</p>}
      {mine.map(f => (
        <div key={f.id} className="kb-file-row">
          <span className="kb-file-ic"><FileText size={15} /></span>
          <button type="button" className="kb-file-name" onClick={() => openFile(f)} title={`Open ${f.original_filename}`}>{f.original_filename}</button>
          <span className="kb-meta whitespace-nowrap">{sizeText(f.size_bytes)}</span>
          <button type="button" className="kb-icon-btn" title="View" aria-label={`View ${f.original_filename}`} onClick={() => openFile(f)}><Eye size={14} /></button>
          <button type="button" className="kb-icon-btn" title="Download" aria-label={`Download ${f.original_filename}`} onClick={() => openFile(f, false)}><Download size={14} /></button>
          {isAdmin && <button type="button" className="kb-icon-btn danger" title="Delete" aria-label={`Delete ${f.original_filename}`} onClick={() => remove(f)}><Trash2 size={14} /></button>}
        </div>
      ))}
      {isAdmin && (
        <>
          <input ref={input} type="file" multiple hidden accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,.doc,.xlsx,.xls,.txt" onChange={e => upload(e.target.files)} />
          <button type="button" className="kb-btn ghost kb-upload" onClick={() => input.current?.click()} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {mine.length ? 'Add another file' : 'Upload document'}
          </button>
        </>
      )}
      {error && <p className="kb-err">{error}</p>}
    </div>
  )
}

/** A modal at page level (not inside the panel), closed by Escape or a click outside. */
export function KbDialog({ label, title, onClose, children, wide = false }: { label: string; title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return createPortal(
    <div className="kb-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`kb-modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-start justify-between gap-3">
          <div><span className="kb-label">{label}</span><h3 className="kb-h" style={{ fontSize: '1.1rem' }}>{title}</h3></div>
          <button className="kb-icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}

/** Paperclip control: faint when nothing is attached, a blue count when there are files; opens the documents dialog. */
export function AttachChip({ ownerKey, label, inline = false }: { ownerKey: string; label: string; inline?: boolean }) {
  const { mine } = useFiles(ownerKey)
  const [open, setOpen] = useState(false)
  const n = mine.length
  return (
    <>
      <button type="button" className={`kb-attach ${n ? 'has' : ''} ${inline ? 'inline' : ''}`} onClick={() => setOpen(true)}
        aria-label={n ? `${n} document${n === 1 ? '' : 's'} for ${label}` : `Attach a document for ${label}`}
        title={n ? `${n} document${n === 1 ? '' : 's'} attached` : 'Attach a document'}>
        <Paperclip size={12} />{n ? <span>{n}</span> : inline ? null : <span>Attach</span>}
      </button>
      {open && (
        <KbDialog label="Supporting documents" title={label} onClose={() => setOpen(false)}>
          <FileList ownerKey={ownerKey} label={label} />
          <p className="kb-hint">Kept in the company document storage (Settings › System). PDF, image, Word, Excel or text.</p>
        </KbDialog>
      )}
    </>
  )
}
