// ---------------------------------------------------------------------------
// App settings now live on the server (Settings page → database). This module keeps a read-only copy of
// the values the screens need so existing code can keep calling loadSettings() synchronously.
// ---------------------------------------------------------------------------
import apiClient from '../api/client'

export interface AppSettings {
  // ── AI Model ──────────────────────────────────────────────────────────────
  defaultModel:       string   // '' = no model selected yet
  tenderModel:        string   // '' = use the default model for tender analysis
  temperature:        number   // 0.0–1.0
  deterministicMode:  boolean  // true → force temp=0.0 + seed
  seed:               number   // used only when deterministicMode=true
  numCtx:             number   // context window (tokens)
  maxTokens:          number   // max output tokens
  // ── Search ────────────────────────────────────────────────────────────────
  topK:               number   // search results (1–50)
  similarityThreshold: number  // min similarity 0.0–1.0 (0 = disabled)
  // ── Prompt Templates ──────────────────────────────────────────────────────
  kbSummaryPrompt:         string
  featureGenInstructions:  string
  eligibilityInstructions: string
}

export const DEFAULT_SETTINGS: AppSettings = {
  defaultModel:            '',
  tenderModel:             '',
  temperature:             0.7,
  deterministicMode:       false,
  seed:                    42,
  numCtx:                  8192,
  maxTokens:               4096,
  topK:                    8,
  similarityThreshold:     0.0,
  kbSummaryPrompt:         '',
  featureGenInstructions:  '',
  eligibilityInstructions: '',
}

// server key → AppSettings field
const KEY_MAP: Record<string, keyof AppSettings> = {
  'ai.default_model': 'defaultModel',
  'tender.model': 'tenderModel',
  'ai.temperature': 'temperature',
  'ai.deterministic': 'deterministicMode',
  'ai.seed': 'seed',
  'ai.num_ctx': 'numCtx',
  'ai.max_tokens': 'maxTokens',
  'search.top_k': 'topK',
  'search.similarity_threshold': 'similarityThreshold',
  'prompts.kb_summary': 'kbSummaryPrompt',
  'prompts.feature_gen': 'featureGenInstructions',
  'prompts.eligibility': 'eligibilityInstructions',
}

let cache: AppSettings = { ...DEFAULT_SETTINGS }

/** Last values fetched from the server (defaults until the first fetch completes). */
export function loadSettings(): AppSettings {
  return cache
}

/** Refresh the copy from the server. Safe to call after login and after saving on the Settings page. */
export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await apiClient.get<Record<string, unknown>>('/settings/effective')
  const next: Record<string, unknown> = { ...DEFAULT_SETTINGS }
  for (const [key, field] of Object.entries(KEY_MAP)) {
    if (key in data) next[field] = data[key]
  }
  cache = next as unknown as AppSettings
  return cache
}
