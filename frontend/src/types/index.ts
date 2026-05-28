export type Role = 'human' | 'assistant'
export type Grounded = true | false | null

export interface Source {
  letter_year: number
  passage: string
  similarity_score: number
  qdrant_point_id: string
}

export interface Message {
  // Stable id: local temp id during stream, real message_id after done
  id: string
  role: Role
  content: string
  grounded: Grounded
  sources: Source[]
  langfuse_trace_id?: string
  created_at: string
  // Streaming state (not persisted)
  isStreaming: boolean
  progressMessage: string | null
  isBlocked: boolean
  isError: boolean
}

export interface Chat {
  chat_id: string
  chat_title: string | null
  model: string
  created_at: string
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  postgres: string
  qdrant: string
  mcp: string
}

export type SSEEventType = 'progress' | 'token' | 'replace' | 'blocked' | 'done' | 'error'

export interface SSEEvent {
  type: SSEEventType
  [key: string]: unknown
}
