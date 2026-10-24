import { useEffect, useState } from 'react'
import apiClient from '../../api/client'

interface AiStatus {
  provider: string
  label?: string
  local?: boolean
  model: string
  reachable: boolean
  problem?: string | null
}

const POLL_MS = 30000

/** Live state of the AI provider: local model ready, provider unreachable, or hosted (data leaves the machine). */
export function useAiStatus() {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () =>
      apiClient.get<AiStatus>('/ai/status')
        .then(r => { if (alive) { setStatus(r.data); setFailed(false) } })
        .catch(() => { if (alive) setFailed(true) })
    load()
    const timer = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(timer) }
  }, [])

  const hosted = !!status && status.local === false
  const name = status?.label ?? status?.provider ?? 'AI'
  if (failed || (status && !status.reachable)) {
    if (failed) return { tone: '#dc2626', label: 'Server unreachable', detail: 'The ZYNEX server did not answer' }
    return hosted
      ? { tone: '#dc2626', label: `${name}: not set up`, detail: status?.problem || 'Finish the setup on Settings > AI Model' }
      : { tone: '#dc2626', label: 'Ollama unreachable', detail: 'Start Ollama to use the AI assistant' }
  }
  if (!status) return { tone: '#9ca3af', label: 'Checking…', detail: 'Checking the AI model' }
  if (hosted) return { tone: '#d97706', label: `Cloud · ${name}`, detail: `Hosted model ${status.model} (text leaves this machine)` }
  return { tone: '#1E9363', label: 'Local · Ready', detail: status.model ? `Local model ${status.model}` : 'Local Ollama model' }
}

export default function AiStatusBadge({ withDetail = false }: { withDetail?: boolean }) {
  const s = useAiStatus()
  return (
    <span
      title={s.detail}
      className="text-[10px] px-2 py-0.5 rounded-full font-medium flex-shrink-0"
      style={{ background: `${s.tone}22`, color: s.tone, border: `1px solid ${s.tone}44` }}
    >
      {s.label}{withDetail ? ` · ${s.detail}` : ''}
    </span>
  )
}
