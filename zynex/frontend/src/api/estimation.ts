import apiClient from './client'

export interface EstimationReport {
  id: number
  document_id: number
  modules_count: number
  total_hours: number
  total_weeks: number
  modules: { modules: Module[] } | null
  tasks: { tasks: Task[] } | null
}

export interface Module {
  name: string
  description: string
  estimated_hours: number
  complexity: string
}

export interface Task {
  name: string
  hours: number
  role: string
  module: string
}

export interface CostSheet {
  id: number
  total_cost: number
  suggested_bid: number
  line_items: Record<string, number> | null
}

export interface ProgressMessage {
  message: string
  level: 'info' | 'working' | 'success' | 'error'
  ts: string
}

export const estimationApi = {
  run: (docId: number) =>
    apiClient.post<EstimationReport>(`/estimation/${docId}/run`),

  get: (docId: number) =>
    apiClient.get<EstimationReport>(`/estimation/${docId}`),

  getCost: (docId: number) =>
    apiClient.get<CostSheet>(`/estimation/${docId}/cost`),

  getProgress: (docId: number) =>
    apiClient.get<{ messages: ProgressMessage[] }>(`/estimation/${docId}/progress`),
}
