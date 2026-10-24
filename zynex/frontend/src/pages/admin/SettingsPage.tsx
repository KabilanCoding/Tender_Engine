import { useCallback, useEffect, useMemo, useState } from 'react'
import { Search, FileCode2, RotateCcw, Save, CheckCircle, ScanSearch, Server, RefreshCw, ChevronRight, ChevronDown, Info, AlertCircle } from 'lucide-react'
import { fetchSettings } from '../../store/settingsStore'
import { settingsApi, type SettingItem } from '../../api/settings'
import { estimationProjectsApi } from '../../api/estimationProjects'
import { Cpu } from '@phosphor-icons/react'
import LlmProviderSection, { llmSectionKeys } from './LlmProviderSection'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Writes, reads back and deletes a small file in the saved document storage, so a wrong address or password shows at once. */
function StorageTest() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  async function run() {
    setBusy(true); setResult(null)
    try {
      const { data } = await settingsApi.testStorage()
      setResult(data.ok
        ? { ok: true, text: `Documents are stored ${data.location === 'file server' ? 'on the file server' : 'on this machine'} in ${data.folder}` }
        : { ok: false, text: data.error || 'The test file could not be written and read back.' })
    } catch (e: any) {
      setResult({ ok: false, text: e?.response?.data?.detail || 'The test could not run.' })
    } finally { setBusy(false) }
  }
  return (
    <div className="mt-5 pt-4 border-t flex flex-wrap items-center gap-3" style={{ borderColor: 'var(--line, rgba(127,127,127,.2))' }}>
      <button type="button" onClick={run} disabled={busy}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-60" style={{ background: '#014BAA' }}>
        {busy ? <RefreshCw size={12} className="animate-spin" /> : <Server size={12} />} Test document storage
      </button>
      <span className="text-xs" style={{ color: 'var(--ink-3)' }}>Uses the saved values: save your changes first.</span>
      {result && (
        <p className="w-full flex items-start gap-1.5 text-xs" role="status" style={{ color: result.ok ? 'var(--s-ok, #15803d)' : 'var(--s-bad, #b91c1c)' }}>
          {result.ok ? <CheckCircle size={13} className="mt-px shrink-0" /> : <AlertCircle size={13} className="mt-px shrink-0" />}{result.text}
        </p>
      )}
    </div>
  )
}

type Tab = 'model' | 'search' | 'prompts' | 'tender' | 'system'
type Values = Record<string, any>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SliderField({
  label, value, min, max, step = 0.01, unit = '', onChange, hint,
}: {
  label: string; value: number; min: number; max: number
  step?: number; unit?: string; onChange: (v: number) => void; hint?: string
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <span className="text-sm font-mono font-semibold tabular-nums px-2 py-0.5 rounded" style={{ color: '#014BAA', background: '#014BAA18' }}>
          {value.toFixed(step < 1 ? 2 : 0)}{unit}
        </span>
      </div>
      {/* Track + thumb */}
      <div className="relative flex items-center h-5">
        {/* Visible track */}
        <div className="absolute w-full h-2 rounded-full overflow-hidden" style={{ background: 'var(--line)' }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: '#014BAA' }} />
        </div>
        {/* Native range input (transparent, on top for interaction) */}
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="relative w-full cursor-pointer"
          style={{
            appearance: 'none',
            WebkitAppearance: 'none',
            background: 'transparent',
            height: '20px',
            margin: 0,
          }}
        />
      </div>
      <style>{`
        input[type=range]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 18px; height: 18px;
          border-radius: 50%;
          background: #014BAA;
          border: 2px solid white;
          box-shadow: 0 1px 4px rgba(1, 75, 170,0.5);
          cursor: pointer;
          margin-top: -8px;
        }
        input[type=range]::-moz-range-thumb {
          width: 16px; height: 16px;
          border-radius: 50%;
          background: #014BAA;
          border: 2px solid white;
          box-shadow: 0 1px 4px rgba(1, 75, 170,0.5);
          cursor: pointer;
        }
        input[type=range]::-webkit-slider-runnable-track { background: transparent; height: 2px; }
        input[type=range]::-moz-range-track { background: transparent; height: 2px; }
        input[type=range]:focus { outline: none; }
      `}</style>
      <div className="flex justify-between mt-1">
        <span className="text-xs text-gray-400">{min}{unit}</span>
        {hint && <span className="text-xs text-gray-400 italic text-center flex-1 mx-2">{hint}</span>}
        <span className="text-xs text-gray-400">{max}{unit}</span>
      </div>
    </div>
  )
}

function NumberField({
  label, value, min, max, onChange, hint,
}: {
  label: string; value: number; min?: number; max?: number
  onChange: (v: number) => void; hint?: string
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
      <input
        type="number" value={value} min={min} max={max}
        onChange={e => onChange(parseInt(e.target.value) || 0)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-[#014BAA] bg-white"
      />
      {hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  )
}

function Toggle({
  label, checked, onChange, hint,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-gray-700">{label}</p>
        {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${
          checked ? 'bg-[#014BAA]' : 'bg-gray-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )
}

function PromptTextarea({
  label, value, placeholder, hint, onChange, onReset,
}: {
  label: string; value: string; placeholder: string; hint?: string
  onChange: (v: string) => void; onReset: () => void
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-sm font-medium text-gray-700">{label}</label>
        <button
          type="button"
          onClick={onReset}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          <RotateCcw size={11} /> Reset to default
        </button>
      </div>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        rows={5}
        className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-sm text-gray-800 font-mono focus:outline-none focus:border-[#014BAA] bg-white resize-y leading-relaxed placeholder-gray-400"
      />
      {hint && <p className="text-xs text-gray-400 mt-1 flex items-start gap-1"><Info size={10} className="mt-0.5 shrink-0" />{hint}</p>}
    </div>
  )
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-3.5 border-b border-gray-100 bg-gray-50">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      <div className="px-5 py-5 space-y-5">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generic field: rendered from the definition the server sends (type, limits, help text)
// ---------------------------------------------------------------------------

const MODEL_KEYS = ['ai.default_model', 'tender.model', 'tender.fallback_model']

function SchemaField({ item, value, onChange, onReset, models }: {
  item: SettingItem
  value: any
  onChange: (v: any) => void
  onReset: () => void
  models: string[]
}) {
  const changed = JSON.stringify(value) !== JSON.stringify(item.default)
  const defaultText = item.default === '' ? 'blank' : String(item.default)
  const footer = (
    <div className="flex items-center justify-between mt-1">
      <p className="text-xs text-gray-400">{item.help}</p>
      {changed && (
        <button type="button" onClick={onReset} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 shrink-0 ml-3">
          <RotateCcw size={10} /> Default: {defaultText.length > 28 ? defaultText.slice(0, 28) + '…' : defaultText}
        </button>
      )}
    </div>
  )

  if (item.type === 'bool') {
    return <Toggle label={item.label} checked={!!value} onChange={onChange} hint={item.help} />
  }
  const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:border-[#014BAA] bg-white'

  let control: React.ReactNode
  if (MODEL_KEYS.includes(item.key)) {
    control = (
      <select value={value ?? ''} onChange={e => onChange(e.target.value)} className={inputCls}>
        <option value="">{item.key === 'ai.default_model' ? '— not selected —' : '— use the default model —'}</option>
        {value && !models.includes(value) && <option value={value}>{value} (not installed)</option>}
        {models.map(m => <option key={m} value={m}>{m}</option>)}
      </select>
    )
  } else if (item.type === 'choice') {
    control = (
      <select value={value} onChange={e => onChange(e.target.value)} className={inputCls}>
        {item.choices.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  } else if (item.type === 'int' || item.type === 'float') {
    control = (
      <input
        type="number" value={value} min={item.min ?? undefined} max={item.max ?? undefined}
        step={item.type === 'float' ? 0.01 : 1}
        onChange={e => {
          const n = item.type === 'float' ? parseFloat(e.target.value) : parseInt(e.target.value, 10)
          if (!Number.isNaN(n)) onChange(n)
        }}
        className={inputCls}
      />
    )
  } else if (item.type === 'text') {
    control = <textarea value={value} rows={4} onChange={e => onChange(e.target.value)} className={inputCls + ' font-mono resize-y'} />
  } else {
    control = <input type="text" value={value ?? ''} onChange={e => onChange(e.target.value)} className={inputCls} />
  }

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1.5">{item.label}</label>
      {control}
      {footer}
    </div>
  )
}

function SchemaGroup({ items, values, set, commit, reset, models }: {
  items: SettingItem[]; values: Values
  set: (key: string, v: any) => void; commit: (key: string, v: any) => void
  reset: (key: string) => void; models: string[]
}) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  const basic = items.filter(i => !i.advanced)
  const advanced = items.filter(i => i.advanced)
  const render = (list: SettingItem[]) => list.map(i => (
    <SchemaField key={i.key} item={i} value={values[i.key]} models={models}
      onChange={v => (MODEL_KEYS.includes(i.key) ? commit(i.key, v) : set(i.key, v))} onReset={() => reset(i.key)} />
  ))
  return (
    <>
      {basic.length > 0 && <div className="space-y-5">{render(basic)}</div>}
      {advanced.length > 0 && (
        <div>
          <button type="button" onClick={() => setShowAdvanced(s => !s)}
            className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-[#014BAA]">
            {showAdvanced ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Advanced ({advanced.length})
          </button>
          {showAdvanced && <div className="space-y-5 mt-4">{render(advanced)}</div>}
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Tab: AI Model
// ---------------------------------------------------------------------------

function ModelTab({ items, values, set, commit, reset, models, loadingModels, reloadModels, nvidiaKey }: {
  items: SettingItem[]; values: Values
  set: (key: string, v: any) => void; commit: (key: string, v: any) => void; reset: (key: string) => void
  models: string[]; loadingModels: boolean; reloadModels: () => void; nvidiaKey: boolean
}) {
  const model = values['ai.default_model'] as string
  const bespoke = ['ai.default_model', 'ai.deterministic', 'ai.seed', 'ai.temperature', 'ai.num_ctx', 'ai.max_tokens']
  const owned = llmSectionKeys('ai')
  const rest = items.filter(i => i.group === 'ai' && !bespoke.includes(i.key) && !owned.has(i.key))
  const provider = values['ai.provider']

  return (
    <div className="space-y-5">
      <LlmProviderSection scope="ai" items={items} values={values} set={set} reset={reset} />

      {provider === 'ollama' && (
      <SectionCard title="Default Model">
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-gray-600">
              The model used for all AI features, including tender analysis. Clicking a model saves it right away.
              Tender analysis can use a different model (Tender Analysis tab).
            </p>
            <button onClick={reloadModels} disabled={loadingModels}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-[#014BAA] transition-colors shrink-0 ml-3">
              <RefreshCw size={12} className={loadingModels ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
          {loadingModels ? (
            <p className="text-sm text-gray-400 italic">Loading models from Ollama…</p>
          ) : models.length === 0 ? (
            <p className="text-sm text-red-500">
              No models found. Make sure Ollama is running and at least one model is pulled
              (e.g. <code className="bg-gray-100 px-1 rounded">ollama pull qwen2.5:14b</code>).
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {models.map(m => (
                <button key={m} type="button" onClick={() => commit('ai.default_model', m)}
                  className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all ${
                    model === m
                      ? 'border-[#014BAA] bg-[#014BAA] text-white'
                      : 'border-gray-300 text-gray-600 hover:border-[#014BAA] hover:text-[#014BAA]'
                  }`}>
                  {m}
                </button>
              ))}
            </div>
          )}
          {!model && (
            <p className="text-xs text-amber-600 mt-3 flex items-center gap-1.5">
              <AlertCircle size={12} /> No model is selected yet: AI features and tender analysis will not run until you pick one.
            </p>
          )}
        </div>
      </SectionCard>
      )}

      <SectionCard title="Generation Behaviour">
        <Toggle
          label="Deterministic mode"
          checked={!!values['ai.deterministic']}
          onChange={v => set('ai.deterministic', v)}
          hint="Forces temperature=0.0 and a fixed seed, so the same input gives the same output. Overrides the temperature slider."
        />
        {values['ai.deterministic'] ? (
          <NumberField label="Seed" value={values['ai.seed']} min={0}
            onChange={v => set('ai.seed', v)} hint="Any integer. Change it to get a different but still reproducible output." />
        ) : (
          <SliderField label="Temperature" value={values['ai.temperature']} min={0} max={1} step={0.01}
            onChange={v => set('ai.temperature', v)} hint="Low = consistent, High = creative. Tender analysis always runs at 0." />
        )}
      </SectionCard>

      <SectionCard title="Context & Output">
        <div className="grid grid-cols-2 gap-5">
          <NumberField label="Context window (tokens)" value={values['ai.num_ctx']} min={2048} max={131072}
            onChange={v => set('ai.num_ctx', v)}
            hint="How much text the model considers at once. Larger = slower. Tender analysis always uses at least 8192." />
          <NumberField label="Max output tokens" value={values['ai.max_tokens']} min={256} max={16384}
            onChange={v => set('ai.max_tokens', v)} hint="Maximum length of the AI's response." />
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-xs text-blue-700 leading-relaxed">
          <strong>Note:</strong> a value larger than the model supports is silently capped by Ollama.
        </div>
      </SectionCard>

      <SectionCard title="Connection &amp; Provider">
        <SchemaGroup items={rest} values={values} set={set} commit={commit} reset={reset} models={models} />
      </SectionCard>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Search
// ---------------------------------------------------------------------------

function SearchTab({ values, set }: { values: Values; set: (key: string, v: any) => void }) {
  return (
    <div className="space-y-5">
      <SectionCard title="Document Search">
        <SliderField label="Top K results" value={values['search.top_k']} min={1} max={50} step={1}
          onChange={v => set('search.top_k', v)} hint="Number of document passages returned by each search" />
        <SliderField label="Similarity threshold" value={values['search.similarity_threshold']} min={0} max={1} step={0.01}
          onChange={v => set('search.similarity_threshold', v)} hint="Passages below this score are filtered out. 0 = no filter" />
      </SectionCard>

      <SectionCard title="About Document Search">
        <div className="space-y-3 text-sm text-gray-600 leading-relaxed">
          <p>
            Uploaded project documents are split into passages and indexed with the <code className="bg-gray-100 px-1 rounded text-xs">nomic-embed-text</code> embedding
            model. A query is embedded the same way and matched to passages by cosine similarity.
          </p>
          <div className="grid grid-cols-2 gap-3">
            {[
              ['Top K', 'How many passages to retrieve. Higher = more context for the AI, but slower.'],
              ['Similarity threshold', 'Minimum score (0–1) for a passage to be included. 0.4–0.6 is a good starting range.'],
            ].map(([t, d]) => (
              <div key={t} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="font-semibold text-gray-700 text-xs mb-1">{t}</p>
                <p className="text-xs text-gray-500">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Prompt Templates
// ---------------------------------------------------------------------------

const PLACEHOLDER_KB = `You are a knowledge-base assistant for a software company.
Answer the user's query based only on the document excerpts provided.
Be concise and cite which projects or documents support your answer.`

const PLACEHOLDER_FEAT = `Additional guidance for feature generation:
- Break down authentication into separate login, register, and password-reset features
- Treat each dashboard widget as a separate sub-feature
- Include DevOps and CI/CD pipeline tasks as a separate module`

const PLACEHOLDER_ELIG = `Additional eligibility guidance:
- Treat optional or preferred items as non-mandatory
- Ignore marketing text and general descriptions of the project`

function PromptsTab({ values, set }: { values: Values; set: (key: string, v: any) => void }) {
  return (
    <div className="space-y-5">
      <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-xs text-amber-700 flex items-start gap-2">
        <Info size={13} className="mt-0.5 shrink-0" />
        <span>Leaving a field empty uses the built-in prompt. Custom text refines the built-in rules; it does not replace them.</span>
      </div>

      <SectionCard title="Knowledge Base Search: Summarisation Prompt">
        <PromptTextarea label="System prompt" value={values['prompts.kb_summary']} placeholder={PLACEHOLDER_KB}
          hint="Sent as the system instruction when summarising search results. Leave blank for the built-in prompt."
          onChange={v => set('prompts.kb_summary', v)} onReset={() => set('prompts.kb_summary', '')} />
      </SectionCard>

      <SectionCard title="Feature Generation: Extra Instructions">
        <PromptTextarea label="Additional instructions" value={values['prompts.feature_gen']} placeholder={PLACEHOLDER_FEAT}
          hint="Appended to the feature-generation prompt. Use it to enforce domain-specific granularity or naming."
          onChange={v => set('prompts.feature_gen', v)} onReset={() => set('prompts.feature_gen', '')} />
      </SectionCard>

      <SectionCard title="Tender Analysis: Extra Instructions">
        <PromptTextarea label="Additional instructions" value={values['prompts.eligibility']} placeholder={PLACEHOLDER_ELIG}
          hint="Added to the tender extraction prompt for every run. The built-in rules and JSON format still apply."
          onChange={v => set('prompts.eligibility', v)} onReset={() => set('prompts.eligibility', '')} />
      </SectionCard>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Settings Page
// ---------------------------------------------------------------------------

const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: 'model',   label: 'AI Model',        icon: <Cpu size={16} /> },
  { key: 'tender',  label: 'Tender Analysis', icon: <ScanSearch size={15} /> },
  { key: 'search',  label: 'Search',          icon: <Search size={15} /> },
  { key: 'prompts', label: 'Prompts',         icon: <FileCode2 size={15} /> },
  { key: 'system',  label: 'System',          icon: <Server size={15} /> },
]

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>('model')
  const [items, setItems] = useState<SettingItem[]>([])
  const [values, setValues] = useState<Values>({})
  const [nvidiaKey, setNvidiaKey] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)

  const [note, setNote] = useState<string | null>(null)

  const apply = useCallback((payload: { settings: SettingItem[]; nvidia_key_configured: boolean }, keepEdits: Values = {}) => {
    setItems(payload.settings)
    // values from the server, with any edits the admin has not saved yet laid back on top
    setValues({ ...Object.fromEntries(payload.settings.map(i => [i.key, i.value])), ...keepEdits })
    setNvidiaKey(payload.nvidia_key_configured)
    fetchSettings().catch(() => { /* the screens refresh on their next load */ })
  }, [])

  useEffect(() => {
    settingsApi.get()
      .then(({ data }) => apply(data))
      .catch(err => setError(err.response?.data?.detail || 'Could not load settings'))
      .finally(() => setLoading(false))
    fetchModels()
  }, [apply])

  async function fetchModels() {
    setLoadingModels(true)
    try {
      const { data } = await estimationProjectsApi.listModels()
      setModels(data.models)
    } finally {
      setLoadingModels(false)
    }
  }

  const dirtyKeys = useMemo(
    () => items.filter(i => JSON.stringify(values[i.key]) !== JSON.stringify(i.value)).map(i => i.key),
    [items, values],
  )

  function set(key: string, value: any) {
    setValues(prev => ({ ...prev, [key]: value }))
    setSaved(false)
    setError(null)
  }

  /** Save one setting immediately (used for model choices) without touching other unsaved edits. */
  async function commit(key: string, value: any) {
    setError(null)
    const before = values[key]
    const otherEdits = Object.fromEntries(dirtyKeys.filter(k => k !== key).map(k => [k, values[k]]))
    setValues(prev => ({ ...prev, [key]: value }))              // show the choice at once
    try {
      const { data } = await settingsApi.save({ [key]: value })
      apply(data, otherEdits)
      setNote(`${items.find(i => i.key === key)?.label ?? key} saved: ${value || 'default'}`)
      setTimeout(() => setNote(null), 4000)
    } catch (err: any) {
      setValues(prev => ({ ...prev, [key]: before }))           // put the old choice back
      setError(err.response?.data?.detail || 'Could not save the setting')
    }
  }

  function handleDiscard() {
    setValues(Object.fromEntries(items.map(i => [i.key, i.value])))
    setError(null)
  }

  async function handleSave() {
    setError(null)
    try {
      const { data } = await settingsApi.save(Object.fromEntries(dirtyKeys.map(k => [k, values[k]])))
      apply(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not save settings')
    }
  }

  async function resetKeys(keys?: string[]) {
    setError(null)
    try {
      const { data } = await settingsApi.reset(keys)
      apply(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Could not reset settings')
    }
  }

  function handleResetAll() {
    if (!window.confirm('Reset ALL settings to their defaults? This applies to every user of the server.')) return
    resetKeys()
  }

  const itemsOf = (group: string) => items.filter(i => i.group === group)

  if (loading) return <p className="text-sm text-gray-400 italic">Loading settings…</p>

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="zx-page-head">
        <div>
          <span className="zx-eyebrow-line">Administration</span>
          <h1 className="mt-1">Settings</h1>
          <p>Shared by everyone on this server. Saved changes apply straight away.</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={handleResetAll}
            className="zx-action whitespace-nowrap hover:!border-red-400 hover:!text-red-500">
            <RotateCcw size={13} /> Reset all
          </button>
          <button onClick={handleSave} disabled={dirtyKeys.length === 0 && !saved}
            className="zx-action primary whitespace-nowrap disabled:opacity-50 disabled:pointer-events-none"
            style={saved ? { background: '#1F7A56', borderColor: '#1F7A56' } : undefined}>
            {saved ? <><CheckCircle size={14} /> Saved</> : <><Save size={14} /> Save changes{dirtyKeys.length > 0 ? ` (${dirtyKeys.length})` : ''}</>}
          </button>
        </div>
      </div>

      {note && (
        <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg px-4 py-2.5 flex items-center gap-2" role="status">
          <CheckCircle size={15} /> {note}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3 flex items-start gap-2" role="alert">
          <AlertCircle size={15} className="mt-0.5 shrink-0" /> <span>{error}</span>
        </div>
      )}

      <div className="flex gap-1 bg-white rounded-xl p-1 shadow-sm border border-gray-200 overflow-x-auto" role="tablist">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} role="tab" aria-selected={tab === t.key}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap shrink-0 ${
              tab === t.key ? 'text-white shadow-sm' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            }`}
            style={tab === t.key ? { backgroundColor: '#014BAA' } : {}}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === 'model' && (
        <ModelTab items={items} values={values} set={set} commit={commit} reset={k => resetKeys([k])} models={models}
          loadingModels={loadingModels} reloadModels={fetchModels} nvidiaKey={nvidiaKey} />
      )}
      {tab === 'tender' && (
        <>
          <LlmProviderSection scope="tender" items={items} values={values} set={set} reset={k => resetKeys([k])} />
          <SectionCard title="Tender Analysis">
            <SchemaGroup items={itemsOf('tender').filter(i => !llmSectionKeys('tender').has(i.key))} values={values} set={set} commit={commit}
              reset={k => resetKeys([k])} models={models} />
          </SectionCard>
        </>
      )}
      {tab === 'search' && <SearchTab values={values} set={set} />}
      {tab === 'prompts' && <PromptsTab values={values} set={set} />}
      {dirtyKeys.length > 0 && (
        <div className="sticky bottom-4 flex justify-end">
          <div className="flex items-center gap-3 bg-white border border-amber-300 shadow-lg rounded-xl px-4 py-2.5">
            <span className="text-xs text-amber-700 font-medium">
              {dirtyKeys.length} unsaved change{dirtyKeys.length > 1 ? 's' : ''}: not applied until you save
            </span>
            <button onClick={handleDiscard} className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1">Discard</button>
            <button onClick={handleSave}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white" style={{ background: '#014BAA' }}>
              <Save size={12} /> Save changes
            </button>
          </div>
        </div>
      )}

      {tab === 'system' && (
        <SectionCard title="System">
          <SchemaGroup items={itemsOf('system')} values={values} set={set} commit={commit} reset={k => resetKeys([k])} models={models} />
          <StorageTest />
        </SectionCard>
      )}
    </div>
  )
}
