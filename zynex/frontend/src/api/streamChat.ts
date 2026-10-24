import { useAuthStore } from '../store/authStore'

interface StreamChatOptions {
  messages:     { role: string; content: string }[]
  model?:       string
  temperature?: number
  system_prompt?: string
  onChunk:      (text: string) => void
  onDone:       () => void
  onError:      (msg: string) => void
}

/**
 * POST /api/v1/ai/chat/stream and stream SSE chunks into onChunk().
 * Uses the same JWT token as the axios apiClient.
 */
export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const token = useAuthStore.getState().token

  let response: Response
  try {
    response = await fetch('/api/v1/ai/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type':  'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        messages:      opts.messages,
        model:         opts.model         || undefined,
        temperature:   opts.temperature   ?? 0.7,
        system_prompt: opts.system_prompt || undefined,
      }),
    })
  } catch {
    opts.onError('Network error — make sure the backend is running.')
    return
  }

  if (!response.ok) {
    opts.onError(`Server error ${response.status}`)
    return
  }

  const reader  = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE lines: "data: ...\n\n"
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''   // keep incomplete last line

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue

      const payload = trimmed.slice(5).trim()
      if (payload === '[DONE]') { opts.onDone(); return }

      try {
        const parsed = JSON.parse(payload)
        if (parsed.error) { opts.onError(parsed.error); return }
        if (parsed.content) opts.onChunk(parsed.content)
      } catch {
        // malformed chunk — skip
      }
    }
  }

  opts.onDone()
}
