/** API layer for the Tender Tiger tab (/api/v1/tender-tiger/*). */
import apiClient from '../../api/client'

export interface TigerRun {
  run_id: string
  state: string            // RUNNING | DONE | FAILED | CANCELLED
  verdict: 'PASS' | 'FAIL' | 'PARTIAL' | null
  met?: number | null      // requirements met in that run
  total?: number | null
  at: string | null
}

export interface TigerTender {
  tid: string
  tender_title: string | null
  organization: string | null
  department: string | null
  key_location: string | null
  tender_type: string | null
  worth: string | null
  worth_amount: number | null
  emd: string | null
  emd_amount: number | null
  doc_fees: string | null
  doc_fee_amount: number | null
  due_date: string | null
  published_date: string | null
  opening_date: string | null
  file_count: number | null
  files_in_db: number | null
  tender_link: string | null
  last_run?: TigerRun | null
  seen?: 'new' | 'viewed' | 'read'      // this user: never opened / opened / marked read
  downloaded_at?: string | null          // when Tender Tiger first saved it
  updated_at?: string | null             // last time its details were refreshed
  analysed_files?: number
}

export interface TigerFile {
  id: string               // "<tid>.<n>": the file's place in the tender folder
  file_name: string
  kind: string
  size: number | null
  analysable: boolean
  last_run?: TigerRun | null
  seen?: 'new' | 'viewed' | 'read'      // this user: never opened / opened / marked read
  on_disk?: boolean         // false when the tender folder is not on this server
}

export interface TigerZipEntry {
  index: number
  name: string
  size: number
  viewable: boolean
}

export interface TigerFilters {
  search: string
  status: string
  org: string
  sort: string
  read?: string          // all | new | unread | read (per user)
}

export interface TigerText {
  file_name: string
  pages: number | null
  characters: number
  truncated: boolean
  text: string
}

export interface TigerTenderDetail extends TigerTender {
  product_description: string | null
  tender_description: string | null
  dept_tender_number: string | null
  quantity: string | null
  startup_relaxation: string | null
  dept_tender_link: string | null
  dept_portal_url: string | null
  scraped_at: string | null
  files: TigerFile[]
}

export interface TigerList {
  items: TigerTender[]
  total: number
  page: number
  page_size: number
  summary: { total: number; open: number; closing_soon: number; organizations: number; new?: number; read?: number }
}

function toError(err: any): Error {
  const detail = err?.response?.data?.detail
  return new Error(typeof detail === 'string' ? detail : err?.message || 'Request failed')
}

function save(blob: Blob, name: string) {
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  a.click()
  URL.revokeObjectURL(href)
}

const blobOf = async (url: string, params?: object) =>
  (await apiClient.get<Blob>(url, { responseType: 'blob', params })).data

export const tigerApi = {
  list: async (params: TigerFilters & { page: number; page_size: number }) =>
    (await apiClient.get<TigerList>('/tender-tiger/tenders', { params })).data,

  organizations: async () => (await apiClient.get<{ name: string; count: number }[]>('/tender-tiger/organizations')).data,

  /** The tenders matching the current filters, as a CSV file. */
  exportCsv: async (filters: TigerFilters) =>
    save(await blobOf('/tender-tiger/export', filters), 'tender-tiger-tenders.csv'),

  markRead: async (tid: string, read = true) =>
    (await apiClient.post<{ tid: string; seen: string }>(`/tender-tiger/tenders/${encodeURIComponent(tid)}/read`, null, { params: { read } })).data,

  detail: async (tid: string) => (await apiClient.get<TigerTenderDetail>(`/tender-tiger/tenders/${encodeURIComponent(tid)}`)).data,

  downloadFile: async (file: TigerFile) => save(await blobOf(`/tender-tiger/files/${file.id}/download`), file.file_name),

  /** Object URL of a stored PDF, for the viewer (the caller revokes it). */
  pdfUrl: async (fileId: string) =>
    URL.createObjectURL(new Blob([await blobOf(`/tender-tiger/files/${fileId}/download`, { inline: true })], { type: 'application/pdf' })),

  text: async (fileId: string) => (await apiClient.get<TigerText>(`/tender-tiger/files/${fileId}/text`)).data,

  zipContents: async (fileId: string) => (await apiClient.get<TigerZipEntry[]>(`/tender-tiger/files/${fileId}/zip`)).data,

  zipEntryBlob: async (fileId: string, index: number) => blobOf(`/tender-tiger/files/${fileId}/zip/${index}`),

  saveBlob: save,

  /** Automatic analysis queue (filled by n8n after each download). */
  queue: async () => (await apiClient.get<AutoQueue>('/tender-tiger/queue')).data,

  /** "Analyse again": re-queue a tender first in line, without the time limit. */
  requeue: async (tid: string) => (await apiClient.post(`/tender-tiger/queue/${encodeURIComponent(tid)}/retry`)).data,

  /** Start the eligibility analysis on a stored file; the caller then opens the progress screen. */
  analyse: async (fileId: string) => {
    try {
      return (await apiClient.post<{ run_id: string; filename: string }>(`/tender-tiger/files/${fileId}/analyse`)).data
    } catch (err) {
      throw toError(err)
    }
  },
}

export function formatMoney(amount: number | null, raw: string | null): string {
  if (amount === null || amount === undefined) return raw || '—'
  if (amount >= 1e7) return `₹ ${(amount / 1e7).toFixed(2)} Cr`
  if (amount >= 1e5) return `₹ ${(amount / 1e5).toFixed(2)} Lakh`
  return `₹ ${amount.toLocaleString('en-IN')}`
}

export function downloadedText(iso?: string | null): string {
  if (!iso) return ''
  const t = new Date(iso), mins = Math.round((Date.now() - t.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (mins < 24 * 60) return `${Math.round(mins / 60)} h ago`
  return t.toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(`${iso}T00:00:00`)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}

/** Days until the due date: positive = open, negative = closed, null = unknown. */
export function daysLeft(iso: string | null): number | null {
  if (!iso) return null
  const due = new Date(`${iso}T00:00:00`).getTime()
  if (isNaN(due)) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  return Math.round((due - today.getTime()) / 86400000)
}

export function formatSize(bytes: number | null): string {
  if (!bytes) return '—'
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

export interface AutoQueueItem {
  tid: string
  status: 'waiting' | 'running' | 'done' | 'failed' | 'stopped' | 'no_documents' | 'skipped'
  priority: number
  reason: string | null
  stage: string | null
  verdict: string | null
  report_id: string | null
  documents: { analyse?: { name: string; role: string; pages: number }[]; skipped?: { name: string; reason: string }[] } | null
  teams_sent_at: string | null
  teams_error: string | null
  finished_at: string | null
  tender_title: string | null
  organization: string | null
  due_date: string | null
}

export interface AutoQueue {
  enabled: boolean
  counts: Record<string, number>
  items: AutoQueueItem[]
}
