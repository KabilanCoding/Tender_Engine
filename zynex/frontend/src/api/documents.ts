import apiClient from './client'

export interface Document {
  id: number
  original_filename: string
  doc_type: string
  status: string
  page_count: number | null
  created_at: string
}

export interface ProgressMessage {
  message: string
  level: 'info' | 'working' | 'success' | 'error'
  ts: string
}

export const documentsApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<Document>('/documents/upload', form)
  },

  list: () => apiClient.get<Document[]>('/documents/'),

  get: (id: number) => apiClient.get<Document>(`/documents/${id}`),

  delete: (id: number) => apiClient.delete(`/documents/${id}`),

  getProgress: (id: number) =>
    apiClient.get<{ messages: ProgressMessage[] }>(`/documents/${id}/progress`),
}
