const STARTERS = [
  'How would Buffett evaluate Apple\'s moat based on his letters?',
  'What did Buffett say about competitive moats in the 1980s?',
  'Compare Coca-Cola\'s business quality using Buffett\'s principles',
]

interface Props {
  onSelect: (query: string) => void
}

export default function EmptyState({ onSelect }: Props) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-8 py-16 text-center">
      {/* Logo mark */}
      <div className="mb-6">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-navy-800 border border-gold/30 mb-4">
          <span className="font-display text-2xl font-bold text-gold">Z</span>
        </div>
        <h1 className="font-display text-3xl font-bold text-cream mb-2">ZimShire</h1>
        <p className="text-cream-600 text-sm font-mono max-w-sm">
          Research companies through Buffett's lens — grounded in primary sources, not generic chatbot guesses.
        </p>
      </div>

      {/* Starter prompts */}
      <div className="w-full max-w-lg space-y-2 mt-4">
        <p className="text-xs text-cream-600 font-mono mb-3 tracking-wider uppercase">
          Try asking
        </p>
        {STARTERS.map((s) => (
          <button
            key={s}
            onClick={() => onSelect(s)}
            className="w-full text-left px-4 py-3 rounded-lg border border-navy-700 bg-navy-800 hover:border-gold/50 hover:bg-navy-700 transition-all text-sm text-cream-200 font-mono leading-snug"
          >
            <span className="text-gold mr-2">→</span>
            {s}
          </button>
        ))}
      </div>

      <p className="mt-8 text-xs text-cream-600/50 font-mono max-w-sm">
        ZimShire provides research support only. Not financial advice.
      </p>
    </div>
  )
}
