import type { Grounded } from '../types'

interface Props {
  grounded: Grounded
}

export default function GroundedBadge({ grounded }: Props) {
  if (grounded === true) {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-400 border border-emerald-700/40">
        <span>✓</span>
        <span>Grounded in Buffett letters</span>
      </span>
    )
  }
  if (grounded === false) {
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-700/40">
        <span>~</span>
        <span>Partially grounded</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-navy-700/60 text-cream-600 border border-navy-600/40">
      <span>—</span>
      <span>Market / web sources</span>
    </span>
  )
}
