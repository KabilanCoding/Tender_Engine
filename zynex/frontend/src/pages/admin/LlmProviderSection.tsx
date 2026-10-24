import { useState } from 'react'
import { CheckCircle, AlertCircle, Loader2, RefreshCw, ShieldAlert, Trash2 } from 'lucide-react'
import { settingsApi, type SettingItem } from '../../api/settings'

// Which AI service to use (local Ollama or a cloud API), with its address, API key and model. Used on both
// Settings > AI Model (scope 'ai') and Settings > Tender Analysis (scope 'tender'). Every value is an ordinary
// setting; they are saved with the page's "Save changes" button.

type Values = Record<string, any>
type Scope = 'tender' | 'ai'

const ALL = {
  default: { id: 'default', label: 'Same as AI Model tab', hint: 'Use the provider chosen on the AI Model tab', cloud: false },
  ollama: { id: 'ollama', label: 'Local · Ollama', hint: 'Runs on your own server. Nothing leaves it', cloud: false },
  nvidia: { id: 'nvidia', label: 'NVIDIA', hint: 'NVIDIA-hosted models', cloud: true },
  openai: { id: 'openai', label: 'OpenAI', hint: 'GPT models', cloud: true },
  anthropic: { id: 'anthropic', label: 'Anthropic', hint: 'Claude models', cloud: true },
  grok: { id: 'grok', label: 'Grok (xAI)', hint: 'Grok models', cloud: true },
  custom: { id: 'custom', label: 'Custom', hint: 'Any OpenAI-compatible service (Groq, Azure, vLLM...)', cloud: true },
} as const

const PROVIDERS_BY_SCOPE: Record<Scope, (keyof typeof ALL)[]> = {
  tender: ['default', 'ollama', 'openai', 'anthropic', 'grok', 'custom'],
  ai: ['ollama', 'nvidia', 'openai', 'anthropic', 'grok', 'custom'],
}

/** Setting keys that hold a provider's address, API key and model (mirrors the server). */
function keysFor(scope: Scope, provider: string) {
  if (scope === 'ai' && provider === 'nvidia') return { url: 'ai.nvidia_base_url', key: 'ai.nvidia_key', model: 'ai.nvidia_model' }
  return { url: `${scope}.${provider}_url`, key: `${scope}.${provider}_key`, model: `${scope}.${provider}_model` }
}

/** Keys this section owns, so the generic list below it does not show them twice. */
export function llmSectionKeys(scope: Scope): Set<string> {
  const keys = new Set<string>([`${scope}.provider`, `${scope}.ollama_url`])
  for (const p of PROVIDERS_BY_SCOPE[scope]) {
    if (p === 'default' || p === 'ollama') continue
    Object.values(keysFor(scope, p)).forEach(k => keys.add(k))
  }
  return keys
}

const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-[#014BAA] bg-white'

export default function LlmProviderSection({ scope, items, values, set, reset }: {
  scope: Scope
  items: SettingItem[]
  values: Values
  set: (key: string, v: any) => void
  reset: (key: string) => void
}) {
  const providers = PROVIDERS_BY_SCOPE[scope].map(id => ALL[id])
  const providerKey = `${scope}.provider`
  const ollamaUrlKey = `${scope}.ollama_url`
  const provider: string = values[providerKey] ?? providers[0].id
  const meta = providers.find(p => p.id === provider) ?? providers[0]
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [cloudModels, setCloudModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)

  const { url: urlKey, key: keyKey, model: modelKey } = keysFor(scope, provider)
  const keyItem = items.find(i => i.key === keyKey)
  const typedKey: string = values[keyKey] ?? ''

  function choose(id: string) {
    set(providerKey, id)
    setResult(null)
    setCloudModels([])
    setModelsError(null)
  }

  const body = () => ({
    provider,
    scope,
    url: (provider === 'ollama' ? values[ollamaUrlKey] : values[urlKey]) || undefined,
    key: typedKey || undefined,                     // blank = the key already saved on the server
    model: values[modelKey] || undefined,
  })

  async function testConnection() {
    setTesting(true)
    setResult(null)
    try {
      const { data } = await settingsApi.testLlm(body())
      setResult(data.ok
        ? { ok: true, text: `Connected in ${data.ms} ms. ${data.reply ?? ''}` }
        : { ok: false, text: data.error ?? 'The service did not accept the request' })
    } catch (err: any) {
      setResult({ ok: false, text: err.response?.data?.detail || 'Could not run the test' })
    } finally {
      setTesting(false)
    }
  }

  async function loadModels() {
    setLoadingModels(true)
    setModelsError(null)
    try {
      const { data } = await settingsApi.listLlmModels(body())
      setCloudModels(data.models)
      if (data.error) setModelsError(data.error)
    } catch (err: any) {
      setModelsError(err.response?.data?.detail || 'Could not load the model list')
    } finally {
      setLoadingModels(false)
    }
  }

  const label = (k: string) => items.find(i => i.key === k)?.label ?? k

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-3.5 border-b border-gray-100 bg-gray-50">
        <h3 className="text-sm font-semibold text-gray-700">{scope === 'tender' ? 'AI service for tender analysis' : 'AI provider'}</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          {scope === 'tender'
            ? 'Choose which AI reads tenders: a model on this server, or a cloud service.'
            : 'The AI used for chat, estimation, proposals and everything else. Tender analysis follows it unless it has its own choice on the Tender Analysis tab.'}
        </p>
      </div>
      <div className="px-5 py-5 space-y-5">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2" role="radiogroup" aria-label="AI service">
          {providers.map(p => {
            const active = provider === p.id
            return (
              <button key={p.id} type="button" role="radio" aria-checked={active} onClick={() => choose(p.id)}
                className={`text-left rounded-lg border px-3 py-2.5 transition-colors ${
                  active ? 'border-[#014BAA] bg-[#014BAA0d] ring-1 ring-[#014BAA]' : 'border-gray-200 hover:border-gray-300 bg-white'}`}>
                <span className="block text-sm font-semibold text-gray-800">{p.label}</span>
                <span className="block text-[11px] text-gray-500 mt-0.5 leading-snug">{p.hint}</span>
              </button>
            )
          })}
        </div>

        {meta.cloud && (
          <div className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
            <ShieldAlert size={14} className="mt-0.5 shrink-0" />
            <span>
              {scope === 'tender' ? 'The tender text' : 'Text sent to the AI (documents, questions, knowledge base excerpts)'} goes to {meta.label}'s
              servers over the internet. Keep to Local · Ollama for confidential material.
            </span>
          </div>
        )}

        {provider === 'default' && (
          <p className="text-xs text-gray-500">Tender analysis follows the provider and model set on the AI Model tab.</p>
        )}

        {provider === 'ollama' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">{label(ollamaUrlKey)}</label>
            <input type="text" value={values[ollamaUrlKey] ?? ''} onChange={e => set(ollamaUrlKey, e.target.value)}
              placeholder={scope === 'tender' ? 'blank = the address on the AI Model tab (http://localhost:11434)' : 'http://localhost:11434'}
              className={inputCls} />
            <p className="text-xs text-gray-400 mt-1">
              {scope === 'tender' ? 'Pick the model in "Tender analysis model" below.' : 'Pick the model under "Default Model" below.'}
            </p>
          </div>
        )}

        {meta.cloud && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Address (URL)</label>
              <input type="text" value={values[urlKey] ?? ''} onChange={e => set(urlKey, e.target.value)}
                placeholder="https://api.example.com/v1" className={inputCls} />
              {provider === 'custom' && <p className="text-xs text-gray-400 mt-1">The base address that ends before /chat/completions.</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">API key</label>
              <div className="flex gap-2">
                <input type="password" autoComplete="new-password" value={typedKey} onChange={e => set(keyKey, e.target.value)}
                  placeholder={keyItem?.configured ? '•••••••••••• saved: type to replace it' : 'Paste the API key'} className={inputCls} />
                {keyItem?.configured && (
                  <button type="button" onClick={() => reset(keyKey)} title="Remove the saved key"
                    className="shrink-0 px-3 rounded-lg border border-gray-300 text-gray-500 hover:text-red-600 hover:border-red-300">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">Stored encrypted on the server and never shown again.</p>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-gray-700">Model</label>
                <button type="button" onClick={loadModels} disabled={loadingModels}
                  className="flex items-center gap-1 text-xs text-[#014BAA] hover:underline disabled:opacity-50">
                  {loadingModels ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />} Load models from the service
                </button>
              </div>
              <input type="text" list={`${scope}-llm-models`} value={values[modelKey] ?? ''} onChange={e => set(modelKey, e.target.value)}
                placeholder="model name" className={inputCls} />
              <datalist id={`${scope}-llm-models`}>{cloudModels.map(m => <option key={m} value={m} />)}</datalist>
              {modelsError && <p className="text-xs text-red-600 mt-1">{modelsError}</p>}
              {cloudModels.length > 0 && !modelsError && (
                <p className="text-xs text-gray-400 mt-1">{cloudModels.length} models available. Click the box to choose one.</p>
              )}
            </div>
          </div>
        )}

        {(provider === 'ollama' || meta.cloud) && (
          <div className="flex items-center gap-3 flex-wrap">
            <button type="button" onClick={testConnection} disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 text-gray-700 hover:border-[#014BAA] hover:text-[#014BAA] disabled:opacity-50">
              {testing && <Loader2 size={12} className="animate-spin" />} Test connection
            </button>
            {result && (
              <span className={`flex items-start gap-1.5 text-xs ${result.ok ? 'text-green-700' : 'text-red-600'}`} role="status">
                {result.ok ? <CheckCircle size={13} className="mt-0.5 shrink-0" /> : <AlertCircle size={13} className="mt-0.5 shrink-0" />}
                <span>{result.text}</span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
