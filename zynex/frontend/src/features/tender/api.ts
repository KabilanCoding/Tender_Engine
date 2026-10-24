/**
 * API layer for the tender screens (/api/v1/tender/*) through the authenticated ZYNEX client.
 */
import apiClient from '../../api/client'

export interface TenderMetrics {
  execution_time_ms?: number
  chunks_processed?: number
  chunks_successful?: number
  llm_candidate_chunks?: number
  concurrency?: number
  grounding_threshold?: number
  total_chunks?: number
  chunks_started?: number
  raw_criteria_found?: number
  criteria_grounded?: number
  actual_llm_api_calls?: number
  successful_calls?: number
  llm_model?: string
  model_source?: string
  num_ctx?: number
}

export interface CriterionResult {
  criterion_id: string
  page_no: number
  field: string
  operator?: string
  status: 'PASS' | 'FAIL' | 'MISSING' | 'NEEDS_REVIEW' | 'INFORMATIONAL' | 'PROVISIONAL' | 'ERROR'
  tender_value: any
  tender_requirement?: string
  title?: string
  requirement?: string
  status_label?: string
  company_value: any
  mandatory: boolean
  source_text: string
  reason?: string
  evidence?: string
  grounded?: boolean
  group?: string | null
}

export interface ChecklistItem {
  id: string
  category: 'eligibility' | 'scope' | 'deliverables' | 'timeline' | 'commercial' | 'submission' | 'evaluation' | 'obligations'
  text: string
  page: number
  compared?: boolean
  closest_wording?: boolean
  found_by?: 'pattern'
}

export interface FullChecklist {
  items: ChecklistItem[]
  labels: Record<string, string>
  compared?: number
  incomplete?: boolean
  metrics?: { windows?: number; failed_windows?: number; raw_items?: number; kept?: number; not_found_in_tender?: number }
}

export interface KeyDate {
  kind: string
  date: string
  time?: string | null
  page: number
  quote: string
  days_left: number
  status: 'passed' | 'today' | 'open'
}

export interface BidderCategory {
  key: string
  name: string
  status: 'ELIGIBLE' | 'PARTIAL' | 'PENDING' | 'NOT_ELIGIBLE'
  summary: string
  counts: Record<string, number>
}

export interface ReportData {
  run_id: string
  filename: string
  verdict: 'PASS' | 'FAIL' | 'PARTIAL'
  summary?: string | null
  mandatory_pass: number
  mandatory_fail: number
  mandatory_missing: number
  mandatory_review_required?: number
  documents_to_prepare?: number
  optional_pass: number
  optional_fail: number
  results: CriterionResult[]
  action_checklist: string[]
  full_checklist?: FullChecklist | null
  groups?: BidderCategory[] | null
  key_dates?: KeyDate[]
  deadline_warning?: string | null
  best_group?: string | null
  missing_documents?: string[]
  metrics: TenderMetrics
}

export interface TenderRunStatus {
  run_id: string
  status: 'pending' | 'processing' | 'done' | 'completed' | 'failed' | 'cancelled'
  progress_step?: string
  metrics?: TenderMetrics
  verdict?: 'PASS' | 'FAIL' | 'PARTIAL'
  error?: string
  messages?: { message: string; level: string; ts: string }[]
}

export interface TenderHistoryItem {
  run_id: string
  filename: string
  status: string
  verdict?: string
  criteria_count: number
  created_at: string
  met?: number | null
  total?: number | null
}

export interface PipelineStageArtifact {
  step: string
  stage_id: string
  status: string
  output: Record<string, any>
}

export interface PipelineStagesResponse {
  run_id: string
  filename: string
  verdict?: string
  stages: PipelineStageArtifact[]
}

/** FastAPI reports errors as {detail}; surface that text instead of "Request failed with status 400". */
function toError(err: any): Error {
  const detail = err?.response?.data?.detail
  return new Error(typeof detail === 'string' ? detail : err?.message || 'Request failed')
}

export const tenderApi = {
  uploadTender: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    // the AI model, limits and extra instructions come from the server-side Settings page
    try {
      const { data } = await apiClient.post<{ run_id: string; filename: string; status: string }>(
        '/tender/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      return data
    } catch (err) {
      throw toError(err)
    }
  },

  getStatus: async (runId: string) => (await apiClient.get<TenderRunStatus>(`/tender/${runId}/status`)).data,

  getReport: async (runId: string) => (await apiClient.get<ReportData>(`/tender/${runId}/report`)).data,

  getStageArtifacts: async (runId: string) =>
    (await apiClient.get<PipelineStagesResponse>(`/tender/${runId}/stages`)).data,

  getHistory: async () => (await apiClient.get<TenderHistoryItem[]>('/tender/history')).data,

  /** Stop a running analysis (the Stop button). */
  cancelRun: async (runId: string) => {
    try {
      await apiClient.post(`/tender/${runId}/cancel`)
    } catch (err) {
      throw toError(err)
    }
  },

  deleteRun: async (runId: string) => {
    try {
      await apiClient.delete(`/tender/${runId}`)
    } catch (err) {
      throw toError(err)
    }
  },

  /** A plain link cannot carry the login token, so fetch the PDF through the client and save it. */
  downloadPdf: async (runId: string) => {
    const res = await apiClient.get<Blob>(`/tender/${runId}/report/pdf`, { responseType: 'blob' })
    const href = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = href
    a.download = `eligibility-report-${runId}.pdf`
    a.click()
    URL.revokeObjectURL(href)
  },
}
