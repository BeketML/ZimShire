import { useState } from 'react'
import type { Source } from '../types'

interface Props {
  sources: Source[]
  onClose: () => void
}

export default function SourcesPanel({ sources, onClose }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <div className="w-72 flex-shrink-0 border-l border-navy-700 bg-navy-800 flex flex-col animate-slide-in">
      <div className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
        <h2 className="font-display text-sm font-semibold text-gold">
          Letter Citations
          <span className="ml-2 text-xs font-mono font-normal text-cream-600">
            {sources.length}
          </span>
        </h2>
        <button
          onClick={onClose}
          className="text-cream-600 hover:text-cream transition-colors text-lg leading-none"
          aria-label="Close sources"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {sources.map((src, i) => (
          <div
            key={src.qdrant_point_id}
            className="border border-navy-700 rounded-lg overflow-hidden"
          >
            <button
              onClick={() => setExpanded(expanded === i ? null : i)}
              className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-navy-700 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-display font-semibold text-gold">
                  {src.letter_year}
                </span>
                <span className="text-xs text-cream-600">
                  score {src.similarity_score.toFixed(2)}
                </span>
              </div>
              <span className="text-cream-600 text-xs">{expanded === i ? '▲' : '▼'}</span>
            </button>
            {expanded === i && (
              <div className="px-3 pb-3 pt-1 border-t border-navy-700">
                <p className="text-xs text-cream-200 leading-relaxed font-mono whitespace-pre-wrap">
                  {src.passage}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
