import type { Source } from '../types'

const BASE = '/api'

export interface ApiMessage {
  message_id: string
  role: 'human' | 'assistant'
  content: string
  grounded: boolean | null
  sources: Source[]
  langfuse_trace_id: string | null
  created_at: string
}

export interface MessagesResponse {
  chat_id: string
  messages: ApiMessage[]
}

export async function getMessages(chatId: string, userId: string): Promise<ApiMessage[]> {
  const res = await fetch(`${BASE}/chats/${chatId}/messages?user_id=${userId}`)
  if (!res.ok) return []
  const data: MessagesResponse = await res.json()
  return data.messages
}

export interface StreamCallbacks {
  onProgress: (stage: string, message: string) => void
  onToken: (content: string) => void
  onReplace: (content: string) => void
  onBlocked: (reason: string) => void
  onDone: (grounded: boolean | null, sources: Source[], messageId: string | null) => void
  onError: (detail: string) => void
}

export async function streamMessage(
  chatId: string,
  userId: string,
  query: string,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}/chats/${chatId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, query }),
    signal,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    callbacks.onError(body.detail ?? `HTTP ${res.status}`)
    return
  }

  if (!res.body) {
    callbacks.onError('No response stream')
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          const event = JSON.parse(raw)
          switch (event.type) {
            case 'progress':
              callbacks.onProgress(event.stage as string, event.message as string)
              break
            case 'token':
              callbacks.onToken(event.content as string)
              break
            case 'replace':
              callbacks.onReplace(event.content as string)
              break
            case 'blocked':
              callbacks.onBlocked(event.reason as string)
              break
            case 'done':
              callbacks.onDone(
                event.grounded as boolean | null,
                (event.sources as Source[]) ?? [],
                event.message_id as string | null,
              )
              break
            case 'error':
              callbacks.onError(event.detail as string)
              break
          }
        } catch {
          // Malformed SSE line — skip
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
