import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Loader2, Send, X } from 'lucide-react'
import { loadSettings } from '../../store/settingsStore'
import { streamChat } from '../../api/streamChat'
import AiStatusBadge, { useAiStatus } from '../common/AiStatusBadge'
import AssistantMark from '../icons/AssistantMark'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  error?: boolean
  loading?: boolean
}

function AssistantChat({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput]       = useState('')
  const [busy, setBusy]         = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)
  const ai = useAiStatus()

  useEffect(() => {
    // follow the conversation, but do not scroll the page when it opens with no messages
    if (messages.length) bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages])

  async function send(override?: string) {
    const q = (override ?? input).trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)

    const cfg = loadSettings()
    const history = [
      ...messages.filter(m => !m.loading && !m.error).map(m => ({ role: m.role, content: m.content })),
      { role: 'user', content: q },
    ]

    const userMsg: Msg = { id: crypto.randomUUID(), role: 'user', content: q }
    const asstId = crypto.randomUUID()
    setMessages(prev => [...prev, userMsg, { id: asstId, role: 'assistant', content: '' }])

    await streamChat({
      messages:    history,
      model:       cfg.defaultModel || undefined,
      temperature: cfg.deterministicMode ? 0.0 : cfg.temperature,
      onChunk: chunk => {
        setMessages(prev => prev.map(m => m.id === asstId ? { ...m, content: m.content + chunk } : m))
      },
      onDone:  () => { setBusy(false); inputRef.current?.focus() },
      onError: msg => {
        setMessages(prev => prev.map(m => m.id === asstId ? { ...m, content: msg, error: true } : m))
        setBusy(false)
        inputRef.current?.focus()
      },
    })
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const suggestions = [
    'How do I estimate a mobile app?',
    'What is REST vs GraphQL?',
    'Explain microservices briefly',
    'Tips for writing a tender proposal',
  ]

  return (
    <div className="zx-assist-panel flex flex-col overflow-hidden" role="dialog" aria-label="AI assistant">
      {/* Header */}
      <div
        className="flex items-center gap-2.5 px-4 py-3 border-b border-gray-100 flex-shrink-0"
        style={{ background: 'linear-gradient(135deg, var(--brand-tint) 0%, var(--panel) 100%)' }}
      >
        <div className="zx-ai-plate w-9 h-9 rounded-xl">
          <AssistantMark size={26} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold leading-none" style={{ color: 'var(--ink)' }}>AI Assistant</p>
          <p className="text-[10px] mt-1 truncate" style={{ color: 'var(--ink-3)' }}>{ai.detail}</p>
        </div>
        <AiStatusBadge />
        <button type="button" onClick={onClose} className="zx-assist-close" aria-label="Close the assistant"><X size={16} /></button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 ? (
          <div className="flex flex-col gap-3 h-full justify-center">
            <p className="text-xs text-gray-400 text-center">Ask me anything — runs fully on your machine</p>
            <div className="grid grid-cols-2 gap-1.5">
              {suggestions.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-[11px] text-gray-600 bg-gray-50 border border-gray-200 rounded-lg px-2.5 py-2 hover:border-[#014BAA] hover:text-[#013D8C] transition-colors leading-snug"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'gap-2 items-start'}`}>
              {msg.role === 'assistant' && (
                <div className="zx-ai-plate w-7 h-7 rounded-full mt-0.5">
                  <AssistantMark size={16} />
                </div>
              )}
              <div className={`max-w-[80%] rounded-xl text-xs leading-relaxed px-3 py-2 ${
                msg.role === 'user'
                  ? 'text-white rounded-tr-sm'
                  : msg.error
                  ? 'bg-red-50 border border-red-200 text-red-600 flex items-start gap-1.5'
                  : 'bg-gray-100 text-gray-800 rounded-tl-sm'
              }`}
                style={msg.role === 'user' ? { background: 'linear-gradient(180deg, #2462C6, #014BAA)' } : {}}
              >
                {msg.loading ? (
                  <span className="flex items-center gap-1.5 text-gray-400"><Loader2 size={11} className="animate-spin" /> Thinking…</span>
                ) : msg.error ? (
                  <><AlertCircle size={11} className="mt-0.5 flex-shrink-0" />{msg.content}</>
                ) : (
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex items-end gap-2 px-3 py-2.5 border-t border-gray-100 flex-shrink-0">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          rows={1}
          disabled={busy}
          placeholder="Ask anything…"
          aria-label="Message the AI assistant"
          className="flex-1 resize-none bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-800 placeholder-gray-400 focus:outline-none focus:border-[#014BAA] focus:bg-white transition-colors disabled:opacity-50"
          style={{ maxHeight: '72px' }}
          onInput={e => {
            const el = e.currentTarget
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 72)}px`
          }}
        />
        <button
          onClick={() => send()}
          disabled={busy || !input.trim()}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white transition-all disabled:opacity-40 flex-shrink-0"
          style={{ background: busy ? '#94a3b8' : 'linear-gradient(180deg, #2462C6, #014BAA)' }}
          aria-label="Send message"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
        </button>
      </div>
    </div>
  )
}


/** Round button in the corner of every page; opens the assistant as a pop-up. The chat stays while it is closed. */
export default function AssistantLauncher() {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open])
  return (
    <>
      {mounted && <div className={`zx-assist-pop ${open ? 'is-open' : ''}`} aria-hidden={!open}><AssistantChat onClose={() => setOpen(false)} /></div>}
      <button type="button" className={`zx-assist-fab ${open ? 'is-open' : ''}`} onClick={() => { setMounted(true); setOpen(v => !v) }}
        aria-label={open ? 'Close the AI assistant' : 'Open the AI assistant'} aria-expanded={open} title="AI assistant">
        {open ? <X size={22} /> : <AssistantMark size={30} />}
      </button>
    </>
  )
}
