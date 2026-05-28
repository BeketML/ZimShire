import { useState, useEffect } from 'react'
import { getHealth } from '../api/health'
import type { HealthStatus } from '../types'

export default function HealthStatus() {
  const [health, setHealth] = useState<HealthStatus | null>(null)

  useEffect(() => {
    let mounted = true
    const check = () => {
      getHealth()
        .then((h) => { if (mounted) setHealth(h) })
        .catch(() => {
          if (mounted) setHealth({ status: 'degraded', postgres: 'error', qdrant: 'error', mcp: 'error' })
        })
    }
    check()
    const id = setInterval(check, 30_000)
    return () => { mounted = false; clearInterval(id) }
  }, [])

  if (!health) return null

  const ok = health.status === 'ok'
  return (
    <div className="flex items-center gap-1.5 px-3 py-2 text-xs text-cream-600">
      <span
        className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-amber-400'} ${ok ? 'shadow-[0_0_4px_#4CAF7D]' : ''}`}
        title={ok ? 'All systems operational' : `Degraded: postgres=${health.postgres} qdrant=${health.qdrant} mcp=${health.mcp}`}
      />
      <span>{ok ? 'Systems operational' : 'Degraded'}</span>
    </div>
  )
}
