interface Props {
  message: string
}

export default function ProgressBadge({ message }: Props) {
  return (
    <div className="flex items-center gap-2 mb-3 animate-fade-in">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-1.5 h-1.5 bg-gold rounded-full animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
      <span className="text-xs text-cream-600 font-mono tracking-wide">{message}</span>
    </div>
  )
}
