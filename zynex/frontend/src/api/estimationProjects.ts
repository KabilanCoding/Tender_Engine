import apiClient from './client'

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface EstimationFeature {
  id: number
  project_id: number
  sort_order: number
  milestone: string | null
  module: string | null
  sub_module: string | null
  feature: string
  data_model_complexity: 'simple' | 'medium' | 'complex' | null
  api_complexity: 'simple' | 'medium' | 'complex' | null
  business_rules_complexity: 'simple' | 'medium' | 'complex' | null
  ui_complexity: 'simple' | 'medium' | 'complex' | null
  fixed_hours: number
  base_hours: number
  total_dev_hours: number
  total_qa_hours: number
  total_hours: number
}

export interface EstimationResource {
  id: number
  project_id: number
  sort_order: number
  role: string
  responsibility: string | null
  count: number
  effort_pct: number
  effort_hours: number
  hourly_rate: number
  total_cost: number
  is_active: boolean
}

export interface ProjectSummary {
  pm_hours: number
  design_arch_hours: number
  spec_uiux_hours: number
  dev_buffer_hours: number
  grand_total_dev: number
}

export interface EstimationProject {
  id: number
  name: string
  status: 'draft' | 'finalized'
  notes: string | null
  document_id: number | null
  complexity_pct: number
  unit_testing_pct: number
  rework_pct: number
  pm_pct: number
  design_arch_pct: number
  spec_uiux_pct: number
  dev_buffer_pct: number
  margin_pct: number
  infra_cost: number
  total_dev_hours: number
  total_qa_hours: number
  grand_total_hours: number
  internal_cost: number
  margin_amount: number
  total_project_cost: number
  created_at: string
  updated_at: string
  features: EstimationFeature[]
  resources: EstimationResource[]
  summary?: ProjectSummary
}

export interface EstimationProjectListItem {
  id: number
  name: string
  status: 'draft' | 'finalized'
  total_project_cost: number
  grand_total_hours: number
  created_at: string
  document_id: number | null
}

export interface ProjectCreate {
  name: string
  document_id?: number | null
  notes?: string | null
}

export interface ProjectUpdate {
  name?: string
  notes?: string
  status?: 'draft' | 'finalized'
  document_id?: number | null
  complexity_pct?: number
  unit_testing_pct?: number
  rework_pct?: number
  pm_pct?: number
  design_arch_pct?: number
  spec_uiux_pct?: number
  dev_buffer_pct?: number
  margin_pct?: number
  infra_cost?: number
}

export interface FeatureCreate {
  sort_order?: number
  milestone?: string | null
  module?: string | null
  sub_module?: string | null
  feature: string
  data_model_complexity?: 'simple' | 'medium' | 'complex' | null
  api_complexity?: 'simple' | 'medium' | 'complex' | null
  business_rules_complexity?: 'simple' | 'medium' | 'complex' | null
  ui_complexity?: 'simple' | 'medium' | 'complex' | null
  fixed_hours?: number
}

export interface FeatureUpdate {
  sort_order?: number
  milestone?: string | null
  module?: string | null
  sub_module?: string | null
  feature?: string
  data_model_complexity?: 'simple' | 'medium' | 'complex' | null
  api_complexity?: 'simple' | 'medium' | 'complex' | null
  business_rules_complexity?: 'simple' | 'medium' | 'complex' | null
  ui_complexity?: 'simple' | 'medium' | 'complex' | null
  fixed_hours?: number
}

export interface ResourceUpdate {
  count?: number
  hourly_rate?: number
  effort_pct?: number
  responsibility?: string
  is_active?: boolean
}

export interface ResourceCreate {
  role: string
  responsibility?: string | null
  count?: number
  effort_pct?: number
  hourly_rate?: number
}

export interface GenerateOptions {
  platform?: 'web' | 'mobile' | 'both'
  tech_stack?: Record<string, string[]>
  model?: string
  temperature?: number
  seed?: number
}

export interface ProgressMessage {
  message: string
  level: 'info' | 'working' | 'success' | 'error'
  ts: string
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

const BASE = '/estimation-projects'

export const estimationProjectsApi = {
  list: () =>
    apiClient.get<EstimationProjectListItem[]>(`${BASE}/`),

  create: (body: ProjectCreate) =>
    apiClient.post<EstimationProject>(`${BASE}/`, body),

  get: (projectId: number) =>
    apiClient.get<EstimationProject>(`${BASE}/${projectId}`),

  update: (projectId: number, body: ProjectUpdate) =>
    apiClient.put<EstimationProject>(`${BASE}/${projectId}`, body),

  delete: (projectId: number) =>
    apiClient.delete(`${BASE}/${projectId}`),

  generate: (projectId: number, options?: GenerateOptions) =>
    apiClient.post<{ message: string; project_id: number }>(`${BASE}/${projectId}/generate`, options ?? {}),

  listModels: () =>
    apiClient.get<{ models: string[] }>(`${BASE}/models`),

  recalculate: (projectId: number) =>
    apiClient.post<EstimationProject>(`${BASE}/${projectId}/recalculate`),

  getProgress: (projectId: number) =>
    apiClient.get<{ messages: ProgressMessage[] }>(`${BASE}/${projectId}/progress`),

  addFeature: (projectId: number, body: FeatureCreate) =>
    apiClient.post<EstimationProject>(`${BASE}/${projectId}/features`, body),

  updateFeature: (projectId: number, featureId: number, body: FeatureUpdate) =>
    apiClient.put<EstimationProject>(`${BASE}/${projectId}/features/${featureId}`, body),

  deleteFeature: (projectId: number, featureId: number) =>
    apiClient.delete<EstimationProject>(`${BASE}/${projectId}/features/${featureId}`),

  updateResource: (projectId: number, resourceId: number, body: ResourceUpdate) =>
    apiClient.put<EstimationProject>(`${BASE}/${projectId}/resources/${resourceId}`, body),

  addResource: (projectId: number, body: ResourceCreate) =>
    apiClient.post<EstimationProject>(`${BASE}/${projectId}/resources`, body),

  deleteResource: (projectId: number, resourceId: number) =>
    apiClient.delete<EstimationProject>(`${BASE}/${projectId}/resources/${resourceId}`),

  chatReestimate: (projectId: number, message: string) =>
    apiClient.post<{ message: string; project_id: number }>(
      `${BASE}/${projectId}/chat-reestimate`,
      { message },
    ),

  getChatProgress: (projectId: number) =>
    apiClient.get<{ messages: ProgressMessage[] }>(`${BASE}/${projectId}/chat-progress`),

  getChatResult: (projectId: number) =>
    apiClient.get<{ advice: string; changed_count: number; project?: EstimationProject; error?: string }>(
      `${BASE}/${projectId}/chat-result`,
    ),
}
