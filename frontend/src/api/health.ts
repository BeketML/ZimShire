import type { HealthStatus } from '../types'

export async function getHealth(): Promise<HealthStatus> {
  const res = await fetch('/api/health', { signal: AbortSignal.timeout(4000) })
  if (!res.ok) return { status: 'degraded', postgres: 'error', qdrant: 'error', mcp: 'error' }
  return res.json()
}
