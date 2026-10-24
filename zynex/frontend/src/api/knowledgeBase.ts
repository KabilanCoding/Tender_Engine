import apiClient from './client'

export interface ProjectDocument {
  id: number
  project_id: number
  doc_category: string
  original_filename: string
  file_size_bytes: number | null
  page_count: number | null
  is_processed: boolean
  processing_error: string | null
  created_at: string | null
}

export interface Client {
  id: number
  name: string
  industry: string | null
  country: string | null
  contact_email: string | null
  notes: string | null
  client_code?: string | null
  client_type?: string | null
  state_region?: string | null
  engagement_status?: string | null
}

export interface Project {
  id: number
  name: string
  description: string | null
  technologies: string[] | null
  team_size: number | null
  duration_weeks: number | null
  total_value: number | null
  status: string
  client_id?: number | null
  project_code?: string | null
  start_date?: string | null
  completion_date?: string | null
  domain?: string | null
  order_no?: string | null
  work_order_date?: string | null
  project_role?: string | null
  evidence_files?: string[] | null
  portfolio_category?: string | null
}

export interface Employee {
  id: number
  name: string
  role: string
  level: string | null
  skills: string[] | null
  hourly_rate: number | null
  is_active: boolean
  employee_code?: string | null
  department?: string | null
  experience_years?: number | null
  qualification?: string | null
  professional_certifications?: string | null
  work_mode?: string | null
  joining_date?: string | null
  is_key_personnel?: boolean | null
  govt_experience_years?: number | null
  relevant_experience_years?: number | null
}

export interface Technology {
  id: number
  name: string
  category: string | null
  proficiency: string | null
  canonical_id?: string | null
  experience_years?: number | null
}

export interface Certification {
  id: number
  name: string
  issuing_body: string | null
  certificate_number: string | null
  valid_until: string | null
  cert_code?: string | null
  issued_on?: string | null
  valid_until_date?: string | null
  status?: string | null
  document_path?: string | null
}

export interface CostParameter {
  id: number
  role: string
  level: string
  hourly_rate: number
  qa_percentage: number
  devops_percentage: number
  contingency_percentage: number
  profit_margin_percentage: number
}

export interface KbFile {
  id: number
  owner_type: string
  owner_key: string
  original_filename: string
  mime_type?: string | null
  size_bytes?: number | null
  note?: string | null
  created_at?: string | null
}

export interface ProfileField { key: string; label: string; kind: string; hint: string; value: string; is_sample: boolean; sensitive: boolean }
export interface ProfileSection { id: string; title: string; fields: ProfileField[] }

export interface FinancialYear {
  id: number
  fiscal_year: number
  annual_turnover: number
  net_profit?: number | null
  net_worth?: number | null
  working_capital?: number | null
  ebitda?: number | null
  gross_assets?: number | null
  total_liabilities?: number | null
  current_ratio?: number | null
  audit_firm?: string | null
  audit_signoff_date?: string | null
  notes?: string | null
}

export interface OemPartner {
  id: number
  oem: string
  product?: string | null
  partner_type?: string | null
  since_year?: number | null
  status?: string | null
  territory?: string | null
  authorization_ref?: string | null
  is_sample?: boolean | null
}

export interface Office {
  id: number
  city: string
  state?: string | null
  office_type?: string | null
  tenure?: string | null
  employee_capacity?: number | null
  address?: string | null
  is_sample?: boolean | null
}

export interface IndexStatus { indexed: number; rows_in_tables: number; out_of_date: number; ready: boolean }

export const kbApi = {
  indexStatus: () => apiClient.get<IndexStatus>('/kb/index/status'),
  rebuildIndex: () => apiClient.post('/kb/index/rebuild'),
  // Clients
  listClients: () => apiClient.get<Client[]>('/kb/clients'),
  createClient: (data: Omit<Client, 'id'>) => apiClient.post<Client>('/kb/clients', data),
  updateClient: (id: number, data: Partial<Client>) => apiClient.put<Client>(`/kb/clients/${id}`, data),
  deleteClient: (id: number) => apiClient.delete(`/kb/clients/${id}`),

  // Projects
  listProjects: () => apiClient.get<Project[]>('/kb/projects'),
  createProject: (data: Omit<Project, 'id'>) => apiClient.post<Project>('/kb/projects', data),
  updateProject: (id: number, data: Partial<Project>) => apiClient.put<Project>(`/kb/projects/${id}`, data),
  deleteProject: (id: number) => apiClient.delete(`/kb/projects/${id}`),

  // Employees
  listEmployees: () => apiClient.get<Employee[]>('/kb/employees'),
  createEmployee: (data: Omit<Employee, 'id'>) => apiClient.post<Employee>('/kb/employees', data),
  updateEmployee: (id: number, data: Partial<Employee>) => apiClient.put<Employee>(`/kb/employees/${id}`, data),
  deleteEmployee: (id: number) => apiClient.delete(`/kb/employees/${id}`),

  // Technologies
  updateTechnology: (id: number, data: Partial<Technology>) => apiClient.put<Technology>(`/kb/technologies/${id}`, data),
  listTechnologies: () => apiClient.get<Technology[]>('/kb/technologies'),
  createTechnology: (data: Omit<Technology, 'id'>) => apiClient.post<Technology>('/kb/technologies', data),
  deleteTechnology: (id: number) => apiClient.delete(`/kb/technologies/${id}`),

  // Certifications
  updateCertification: (id: number, data: Partial<Certification>) => apiClient.put<Certification>(`/kb/certifications/${id}`, data),
  listCertifications: () => apiClient.get<Certification[]>('/kb/certifications'),
  createCertification: (data: Omit<Certification, 'id'>) => apiClient.post<Certification>('/kb/certifications', data),
  deleteCertification: (id: number) => apiClient.delete(`/kb/certifications/${id}`),

  // Company master: registrations, financial years, OEM partners, offices
  getProfile: () => apiClient.get<{ sections: ProfileSection[] }>('/kb/company-profile'),
  saveProfile: (values: Record<string, string>, confirm: string[] = []) =>
    apiClient.put<{ sections: ProfileSection[] }>('/kb/company-profile', { values, confirm }),
  listFinancials: () => apiClient.get<FinancialYear[]>('/kb/financials'),
  createFinancial: (d: Omit<FinancialYear, 'id'>) => apiClient.post<FinancialYear>('/kb/financials', d),
  updateFinancial: (id: number, d: Omit<FinancialYear, 'id'>) => apiClient.put<FinancialYear>(`/kb/financials/${id}`, d),
  deleteFinancial: (id: number) => apiClient.delete(`/kb/financials/${id}`),
  listOem: () => apiClient.get<OemPartner[]>('/kb/oem-partnerships'),
  createOem: (d: Omit<OemPartner, 'id'>) => apiClient.post<OemPartner>('/kb/oem-partnerships', d),
  updateOem: (id: number, d: Omit<OemPartner, 'id'>) => apiClient.put<OemPartner>(`/kb/oem-partnerships/${id}`, d),
  confirmOem: (id: number) => apiClient.post<OemPartner>(`/kb/oem-partnerships/${id}/confirm`),
  deleteOem: (id: number) => apiClient.delete(`/kb/oem-partnerships/${id}`),
  listOffices: () => apiClient.get<Office[]>('/kb/offices'),
  createOffice: (d: Omit<Office, 'id'>) => apiClient.post<Office>('/kb/offices', d),
  updateOffice: (id: number, d: Omit<Office, 'id'>) => apiClient.put<Office>(`/kb/offices/${id}`, d),
  confirmOffice: (id: number) => apiClient.post<Office>(`/kb/offices/${id}/confirm`),
  deleteOffice: (id: number) => apiClient.delete(`/kb/offices/${id}`),

  // Cost Parameters
  listCostParams: () => apiClient.get<CostParameter[]>('/kb/cost-parameters'),
  updateCostParam: (id: number, data: Partial<CostParameter>) =>
    apiClient.put<CostParameter>(`/kb/cost-parameters/${id}`, data),

  // Dev utilities

  // Project Documents
  listProjectDocuments: (projectId: number) =>
    apiClient.get<ProjectDocument[]>(`/kb/projects/${projectId}/documents`),
  uploadProjectDocument: (projectId: number, formData: FormData) =>
    apiClient.post<ProjectDocument>(`/kb/projects/${projectId}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  deleteProjectDocument: (projectId: number, docId: number) =>
    apiClient.delete(`/kb/projects/${projectId}/documents/${docId}`),
  projectDocumentBlob: (projectId: number, docId: number, inline = true) =>
    apiClient.get<Blob>(`/kb/projects/${projectId}/documents/${docId}/download`, { params: { inline }, responseType: 'blob' }),
  listDocumentChunks: (projectId: number, docId: number) =>
    apiClient.get<{ id: number; chunk_index: number; section_heading: string | null; chunk_text: string }[]>(
      `/kb/projects/${projectId}/documents/${docId}/chunks`
    ),

  // Documents kept for knowledge-base facts (PAN, GSTIN, certificates ...)
  listFiles: (ownerType?: string, ownerKey?: string) =>
    apiClient.get<KbFile[]>('/kb/files', { params: { owner_type: ownerType, owner_key: ownerKey } }),
  uploadFile: (ownerType: string, ownerKey: string, file: File) => {
    const fd = new FormData()
    fd.append('owner_type', ownerType); fd.append('owner_key', ownerKey); fd.append('file', file)
    return apiClient.post<KbFile>('/kb/files', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  deleteFile: (id: number) => apiClient.delete(`/kb/files/${id}`),
  fileBlob: (id: number, inline = true) =>
    apiClient.get<Blob>(`/kb/files/${id}/download`, { params: { inline }, responseType: 'blob' }),

  // Search summarization
  summarizeSearch: (query: string, chunks: object[], opts?: { system_prompt?: string; temperature?: number; model?: string }) =>
    apiClient.post<{ summary: string }>('/kb/search/summarize', { query, chunks, ...opts }),
}
