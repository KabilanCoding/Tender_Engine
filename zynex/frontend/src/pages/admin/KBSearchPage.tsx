import { useEffect, useRef, useState } from 'react'
import { Send, AlertCircle, Loader2, Plus, Trash2, ChevronDown, ChevronUp, Database } from 'lucide-react'
import apiClient from '../../api/client'
import { kbApi } from '../../api/knowledgeBase'
import { loadSettings } from '../../store/settingsStore'
import { streamChat } from '../../api/streamChat'
import AiStatusBadge from '../../components/common/AiStatusBadge'
import AssistantMark from '../../components/icons/AssistantMark'
import { BookOpenText, ChatCircleText, ChatCenteredText } from '@phosphor-icons/react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Mode = 'kb' | 'ai'

interface SearchResult {
  id: number
  project_id: number
  chunk_text: string
  section_heading: string | null
  doc_category: string | null
  similarity: number
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SearchResult[]
  error?: boolean
  loading?: boolean
  ts: string
}

interface ChatSession {
  id: string
  title: string
  mode: Mode
  messages: ChatMessage[]
  createdAt: string
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'zynex_kb_chat_sessions'

function loadSessions(): ChatSession[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch { return [] }
}
function saveSessions(s: ChatSession[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}
function newSession(mode: Mode): ChatSession {
  return { id: crypto.randomUUID(), title: 'New chat', mode, messages: [], createdAt: new Date().toISOString() }
}

// ---------------------------------------------------------------------------
// Source chips
// ---------------------------------------------------------------------------

function SourcesPanel({ sources }: { sources: SearchResult[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        <Database size={11} />
        {sources.length} source{sources.length !== 1 ? 's' : ''}
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {sources.map(s => (
            <div key={s.id} className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs">
              <div className="flex items-center gap-2 mb-1">
                {s.section_heading && <span className="font-semibold text-gray-700">{s.section_heading}</span>}
                {s.doc_category && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                    {s.doc_category.replace(/_/g, ' ')}
                  </span>
                )}
                <span className="text-gray-400 ml-auto">Project #{s.project_id} · {(s.similarity * 100).toFixed(0)}%</span>
              </div>
              <p className="text-gray-500 leading-relaxed line-clamp-3">{s.chunk_text}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({ msg, mode }: { msg: ChatMessage; mode: Mode }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[75%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white leading-relaxed"
          style={{ background: mode === 'kb' ? '#014BAA' : '#0A2150' }}
        >
          {msg.content}
        </div>
      </div>
    )
  }

  const avatarBg = mode === 'kb'
    ? 'linear-gradient(135deg, #0A2150 0%, #014BAA 100%)'
    : 'linear-gradient(135deg, #0A2150 0%, #1F7A56 100%)'

  return (
    <div className="flex gap-3 items-start">
      <div className={`w-8 h-8 rounded-full flex-shrink-0 mt-0.5 ${mode === 'kb' ? 'flex items-center justify-center' : 'zx-ai-plate'}`} style={mode === 'kb' ? { background: avatarBg } : undefined}>
        {mode === 'kb' ? <BookOpenText size={16} className="text-white" /> : <AssistantMark size={19} />}
      </div>
      <div className="flex-1 min-w-0">
        {msg.loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm py-1">
            <Loader2 size={14} className="animate-spin" />
            <span className="animate-pulse">{mode === 'kb' ? 'Searching knowledge base…' : 'Thinking…'}</span>
          </div>
        ) : msg.error ? (
          <div className="flex items-center gap-2 text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <AlertCircle size={14} />{msg.content}
          </div>
        ) : (
          <div className="rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-gray-800" style={{ background: 'var(--panel-2)', border: '1px solid #e5e8ec' }}>
            <p className="whitespace-pre-wrap">{msg.content}</p>
            {msg.sources && msg.sources.length > 0 && <SourcesPanel sources={msg.sources} />}
          </div>
        )}
        <p className="text-[10px] text-gray-400 mt-1 ml-1">{new Date(msg.ts).toLocaleTimeString()}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ mode, onSend }: { mode: Mode; onSend: (q: string) => void }) {
  const kbSuggestions = [
    'Which projects used React as the frontend?',
    'Show projects with Spring Boot backend',
    'Find projects with mobile app features',
    'Which projects involved e-commerce?',
  ]
  const aiSuggestions = [
    'Explain microservices architecture',
    'What is the difference between REST and GraphQL?',
    'How do I estimate software project effort?',
    'Best practices for mobile app security',
  ]
  const suggestions = mode === 'kb' ? kbSuggestions : aiSuggestions

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-6">
      <div className="flex flex-col items-center gap-3">
        <div className={`w-16 h-16 rounded-2xl ${mode === 'kb' ? 'flex items-center justify-center' : 'zx-ai-plate'}`}
          style={mode === 'kb' ? { background: 'linear-gradient(135deg, #0A2150, #014BAA)' } : undefined}>
          {mode === 'kb' ? <BookOpenText size={32} className="text-white" /> : <AssistantMark size={40} />}
        </div>
        <div className="text-center">
          <h2 className="text-base font-semibold text-gray-800">{mode === 'kb' ? 'KB Assistant' : 'AI Chat'}</h2>
          <p className="text-sm text-gray-400 mt-0.5">
            {mode === 'kb'
              ? 'Ask anything about your indexed projects and documents'
              : 'Chat directly with your local AI — fully offline'}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 w-full max-w-md">
        {suggestions.map(s => (
          <button key={s} onClick={() => onSend(s)}
            className="text-left text-xs text-gray-600 bg-white border border-gray-200 rounded-xl px-3 py-2.5 hover:border-[#014BAA] hover:text-[#014BAA] transition-colors leading-snug">
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Mode toggle pills
// ---------------------------------------------------------------------------

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
      <button
        onClick={() => onChange('kb')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
          mode === 'kb' ? 'bg-white text-[#014BAA] shadow-sm' : 'text-gray-500 hover:text-gray-700'
        }`}
      >
        <BookOpenText size={14} /> KB Search
      </button>
      <button
        onClick={() => onChange('ai')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
          mode === 'ai' ? 'bg-white text-[#1F7A56] shadow-sm' : 'text-gray-500 hover:text-gray-700'
        }`}
      >
        <ChatCircleText size={14} /> AI Chat
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function KBSearchPage() {
  const [sessions, setSessions]   = useState<ChatSession[]>(loadSessions)
  const [activeId, setActiveId]   = useState<string | null>(() => loadSessions()[0]?.id ?? null)
  const [mode, setMode]           = useState<Mode>('kb')
  const [input, setInput]         = useState('')
  const [busy, setBusy]           = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  const filteredSessions = sessions.filter(s => s.mode === mode)
  const activeSession    = sessions.find(s => s.id === activeId && s.mode === mode) ?? null

  useEffect(() => { saveSessions(sessions) }, [sessions])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [activeSession?.messages])

  // When switching modes, switch to the first session of that mode (or none)
  function switchMode(m: Mode) {
    setMode(m)
    const first = sessions.find(s => s.mode === m)
    setActiveId(first?.id ?? null)
    setInput('')
  }

  function startNewChat() {
    const s = newSession(mode)
    setSessions(prev => [s, ...prev])
    setActiveId(s.id)
    setInput('')
  }

  function deleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      if (activeId === id) setActiveId(next.find(s => s.mode === mode)?.id ?? null)
      return next
    })
  }

  function updateSession(id: string, updater: (s: ChatSession) => ChatSession) {
    setSessions(prev => prev.map(s => s.id === id ? updater(s) : s))
  }

  async function send(queryOverride?: string) {
    const q = (queryOverride ?? input).trim()
    if (!q || busy) return

    let sessionId = activeId
    if (!sessionId || !sessions.find(s => s.id === sessionId && s.mode === mode)) {
      const s = newSession(mode)
      setSessions(prev => [s, ...prev])
      setActiveId(s.id)
      sessionId = s.id
    }

    setInput('')
    setBusy(true)

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: q, ts: new Date().toISOString() }

    if (mode === 'ai') {
      // ── AI Chat: streaming path ───────────────────────────────────────────
      const cfg = loadSettings()

      // Snapshot history BEFORE appending userMsg (so we include it below)
      const currentSession = sessions.find(s => s.id === sessionId)
      const history = [
        ...(currentSession?.messages ?? []).filter(m => !m.loading && !m.error).map(m => ({ role: m.role, content: m.content })),
        { role: 'user', content: q },
      ]

      const asstId = crypto.randomUUID()
      const asstMsg: ChatMessage = { id: asstId, role: 'assistant', content: '', ts: new Date().toISOString() }

      updateSession(sessionId, s => ({
        ...s,
        title: s.messages.length === 0 ? q.slice(0, 48) : s.title,
        messages: [...s.messages, userMsg, asstMsg],
      }))

      await streamChat({
        messages:    history,
        model:       cfg.defaultModel || undefined,
        temperature: cfg.deterministicMode ? 0.0 : cfg.temperature,
        onChunk: chunk => {
          setSessions(prev => prev.map(s => {
            if (s.id !== sessionId) return s
            return { ...s, messages: s.messages.map(m => m.id === asstId ? { ...m, content: m.content + chunk } : m) }
          }))
        },
        onDone: () => { setBusy(false); inputRef.current?.focus() },
        onError: msg => {
          setSessions(prev => prev.map(s => {
            if (s.id !== sessionId) return s
            return { ...s, messages: s.messages.map(m => m.id === asstId ? { ...m, content: msg, error: true } : m) }
          }))
          setBusy(false)
          inputRef.current?.focus()
        },
      })
      return
    }

    // ── KB Search: non-streaming path ────────────────────────────────────────
    const loadingMsg: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', loading: true, ts: new Date().toISOString() }
    updateSession(sessionId, s => ({
      ...s,
      title: s.messages.length === 0 ? q.slice(0, 48) : s.title,
      messages: [...s.messages, userMsg, loadingMsg],
    }))

    try {
      const cfg = loadSettings()
      const searchRes = await apiClient.get<SearchResult[]>('/kb/search', { params: { q, top_k: cfg.topK } })
      const sources = searchRes.data

      let answer = ''
      if (sources.length === 0) {
        answer = 'No matching documents found in the knowledge base. Try uploading and indexing more project documents.'
      } else {
        try {
          const sumRes = await kbApi.summarizeSearch(q, sources as object[], {
            model:         cfg.defaultModel   || undefined,
            temperature:   cfg.deterministicMode ? 0.0 : cfg.temperature,
            system_prompt: cfg.kbSummaryPrompt || undefined,
          })
          answer = sumRes.data.summary
        } catch {
          answer = 'I found relevant documents but the AI summary is temporarily unavailable. Check the sources below.'
        }
      }

      const assistantMsg: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: answer, sources, ts: new Date().toISOString() }
      updateSession(sessionId, s => ({ ...s, messages: [...s.messages.filter(m => !m.loading), assistantMsg] }))
    } catch (err: any) {
      const errMsg: ChatMessage = {
        id: crypto.randomUUID(), role: 'assistant',
        content: err?.response?.data?.detail || 'Request failed. Make sure the backend is running.',
        error: true, ts: new Date().toISOString(),
      }
      updateSession(sessionId, s => ({ ...s, messages: [...s.messages.filter(m => !m.loading), errMsg] }))
    } finally {
      setBusy(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const modeAccent = mode === 'kb' ? '#014BAA' : '#1F7A56'

  return (
    <div className="flex h-full overflow-hidden gap-3 p-3">

      {/* ── SIDEBAR ── */}
      <div className="zx-subrail w-64 flex-shrink-0 flex flex-col">
        {/* Mode toggle */}
        <div className="px-3 pt-4 pb-2">
          <ModeToggle mode={mode} onChange={switchMode} />
        </div>

        {/* New chat */}
        <div className="px-3 pb-3">
          <button
            onClick={startNewChat}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-700 hover:text-gray-900 hover:bg-gray-100 transition-colors border border-gray-200 hover:border-gray-300"
          >
            <Plus size={14} /> New chat
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
          {filteredSessions.length === 0 && (
            <p className="text-[11px] text-gray-500 text-center py-6 px-3">No chats yet. Start one above.</p>
          )}
          {filteredSessions.map(s => (
            <button
              key={s.id}
              onClick={() => setActiveId(s.id)}
              className={`group w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-colors ${
                activeId === s.id ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
              }`}
            >
              <ChatCenteredText size={14} className="flex-shrink-0 opacity-70" />
              <span className="flex-1 min-w-0 text-xs truncate">{s.title}</span>
              <button
                onClick={e => deleteSession(s.id, e)}
                className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all flex-shrink-0"
              >
                <Trash2 size={11} />
              </button>
            </button>
          ))}
        </div>

        {/* Mode label at bottom */}
        <div className="px-4 py-3 border-t border-gray-200">
          <p className="text-[10px] text-gray-500">
            {mode === 'kb'
              ? <span className="inline-flex items-center gap-1.5"><BookOpenText size={12} /> Answers from your knowledge base</span>
              : <span className="inline-flex items-center gap-1.5"><AssistantMark size={12} /> Local model · fully offline</span>}
          </p>
        </div>
      </div>

      {/* ── MAIN AREA ── */}
      <div className="zx-subpane flex-1 flex flex-col min-w-0">
        {/* Top bar with mode label */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-gray-200 bg-white">
          <div className="flex items-center gap-2">
            {mode === 'kb'
              ? <><BookOpenText size={16} style={{ color: modeAccent }} /><span className="text-sm font-semibold" style={{ color: modeAccent }}>Knowledge Base Search</span></>
              : <><ChatCircleText size={16} style={{ color: modeAccent }} /><span className="text-sm font-semibold" style={{ color: modeAccent }}>AI Chat</span></>
            }
            {activeSession && (
              <span className="text-xs text-gray-400 ml-1 truncate max-w-xs">— {activeSession.title}</span>
            )}
          </div>
          {mode === 'ai' && (
            <AiStatusBadge withDetail />
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
          {!activeSession || activeSession.messages.length === 0
            ? <EmptyState mode={mode} onSend={q => send(q)} />
            : activeSession.messages.map(msg => <MessageBubble key={msg.id} msg={msg} mode={mode} />)
          }
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="border-t border-gray-200 bg-white px-4 py-3">
          <div className="flex items-end gap-2 max-w-3xl mx-auto">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={busy}
              placeholder={mode === 'kb'
                ? 'Ask about your projects, technologies, clients…'
                : 'Ask me anything — running fully offline on your machine…'
              }
              className="flex-1 resize-none bg-gray-50 border border-gray-300 rounded-xl px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none transition-colors disabled:opacity-50"
              style={{ maxHeight: '120px', overflowY: 'auto' }}
              onFocus={e => { e.currentTarget.style.borderColor = modeAccent; e.currentTarget.style.background = '#fff' }}
              onBlur={e => { e.currentTarget.style.borderColor = ''; e.currentTarget.style.background = '' }}
              onInput={e => {
                const el = e.currentTarget
                el.style.height = 'auto'
                el.style.height = `${Math.min(el.scrollHeight, 120)}px`
              }}
            />
            <button
              onClick={() => send()}
              disabled={busy || !input.trim()}
              className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-white transition-all disabled:opacity-40"
              style={{ background: busy ? '#94a3b8' : modeAccent }}
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
          <p className="text-center text-[10px] text-gray-400 mt-1.5">
            <kbd className="bg-gray-100 px-1 py-0.5 rounded text-[9px]">Enter</kbd> send ·{' '}
            <kbd className="bg-gray-100 px-1 py-0.5 rounded text-[9px]">Shift+Enter</kbd> new line
          </p>
        </div>
      </div>
    </div>
  )
}
