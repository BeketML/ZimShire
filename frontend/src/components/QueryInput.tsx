import { useState, useRef, useEffect, KeyboardEvent } from 'react'

interface Props {
  onSend: (query: string) => void
  disabled: boolean
  onStop?: () => void
}

export default function QueryInput({ onSend, disabled, onStop }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  return (
    <div className="border-t border-navy-700 bg-navy-800 px-4 py-3">
      <div className="flex items-end gap-3 bg-navy-700 border border-navy-600 rounded-xl px-4 py-3 focus-within:border-gold/50 transition-colors">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? 'Thinking…' : "Ask about a company, Buffett's philosophy, market data…"}
          rows={1}
          className="flex-1 bg-transparent resize-none outline-none text-sm text-cream font-mono placeholder-cream-600/50 leading-relaxed min-h-[24px] disabled:opacity-50"
        />

        {disabled ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-red-900/40 border border-red-700/40 hover:bg-red-800/50 text-red-400 transition-colors"
            title="Stop generation"
          >
            <span className="w-3 h-3 bg-red-400 rounded-sm" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!value.trim()}
            className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-lg bg-gold disabled:bg-navy-600 hover:bg-gold-light disabled:hover:bg-navy-600 transition-colors"
            title="Send (Enter)"
          >
            <svg className="w-4 h-4 text-navy" viewBox="0 0 16 16" fill="currentColor">
              <path d="M2 8l12-6-4 6 4 6z" />
            </svg>
          </button>
        )}
      </div>
      <p className="text-xs text-cream-600/40 font-mono mt-2 text-center">
        Enter to send · Shift+Enter for new line · ZimShire provides research only, not financial advice
      </p>
    </div>
  )
}
