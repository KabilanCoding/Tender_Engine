import apiClient from './client'

export type SettingType = 'int' | 'float' | 'bool' | 'str' | 'text' | 'choice' | 'secret'

export interface SettingItem {
  key: string
  group: 'ai' | 'search' | 'prompts' | 'tender' | 'system'
  type: SettingType
  label: string
  help: string
  value: any
  default: any
  saved: boolean          // true when an admin changed it from the default
  min: number | null
  max: number | null
  choices: string[]
  advanced: boolean
  configured?: boolean    // secrets only: true when a key is saved (the key itself is never sent to the browser)
}

export interface SettingsPayload {
  groups: string[]
  settings: SettingItem[]
  nvidia_key_configured: boolean
}

export interface LlmProbe {
  provider: string
  scope?: 'tender' | 'ai'   // which tab's saved entries to fall back on
  url?: string
  key?: string      // blank = use the key already saved for this provider
  model?: string
}

export const settingsApi = {
  testLlm: (b: LlmProbe) => apiClient.post<{ ok: boolean; ms?: number; reply?: string; error?: string }>('/settings/llm/test', b),
  listLlmModels: (b: LlmProbe) => apiClient.post<{ models: string[]; error: string | null }>('/settings/llm/models', b),
  testStorage: () => apiClient.post<{ ok: boolean; location: string; folder?: string; error?: string }>('/settings/storage/test'),
  get: () => apiClient.get<SettingsPayload>('/settings'),
  save: (values: Record<string, any>) => apiClient.put<SettingsPayload>('/settings', { values }),
  reset: (keys?: string[]) => apiClient.post<SettingsPayload>('/settings/reset', { keys: keys ?? null }),
}
