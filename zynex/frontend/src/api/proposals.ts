import apiClient from './client'

export interface Proposal {
  id: number
  document_id: number
  technical_proposal: string | null
  commercial_proposal: string | null
  sections: Record<string, string> | null
  docx_path: string | null
  pdf_path: string | null
}

export const proposalsApi = {
  generate: (docId: number) =>
    apiClient.post<Proposal>(`/proposals/${docId}/generate`),

  /** document ids that already have a proposal */
  existing: () => apiClient.get<number[]>('/proposals/'),

  get: (docId: number) =>
    apiClient.get<Proposal>(`/proposals/${docId}`),

  downloadDocx: (docId: number) => downloadFile(`/proposals/${docId}/download/docx`, `proposal_${docId}.docx`),

  downloadPdf: (docId: number) => downloadFile(`/proposals/${docId}/download/pdf`, `proposal_${docId}.pdf`),
}

// window.open cannot send the JWT, so fetch as a blob through the authenticated client
async function downloadFile(url: string, filename: string): Promise<void> {
  const res = await apiClient.get<Blob>(url, { responseType: 'blob' })
  const href = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}
