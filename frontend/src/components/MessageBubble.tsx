import { useMemo } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { Message } from '../types'
import StreamingCursor from './StreamingCursor'
import ProgressBadge from './ProgressBadge'
import GroundedBadge from './GroundedBadge'

// Configure marked for safe rendering
marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text: string): string {
  const raw = marked.parse(text) as string
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS: ['p','h1','h2','h3','h4','strong','em','ul','ol','li','code','pre','blockquote','hr','br','a','span'], ALLOWED_ATTR: ['href','class'] })
}

interface Props {
  message: Message
  onShowSources: () => void
}

export default function MessageBubble({ message, onShowSources }: Props) {
  const html = useMemo(
    () => (message.role === 'assistant' && message.content ? renderMarkdown(message.content) : ''),
    [message.content, message.role],
  )

  if (message.role === 'human') {
    return (
      <div className="flex justify-end mb-6 animate-fade-in">
        <div className="max-w-[70%] bg-navy-700 border border-navy-600 rounded-2xl rounded-tr-sm px-4 py-3">
          <p className="text-cream text-sm font-mono leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex gap-3 mb-6 animate-fade-in">
      {/* Avatar */}
      <div className="flex-shrink-0 w-7 h-7 rounded-lg bg-navy-700 border border-gold/30 flex items-center justify-center mt-0.5">
        <span className="font-display text-xs font-bold text-gold">Z</span>
      </div>

      <div className="flex-1 min-w-0">
        {/* Progress indicator */}
        {message.progressMessage && <ProgressBadge message={message.progressMessage} />}

        {/* Message content */}
        {message.isBlocked ? (
          <div className="bg-amber-900/20 border border-amber-700/30 rounded-xl px-4 py-3">
            <p className="text-amber-300 text-sm font-mono leading-relaxed">
              ⚠ {message.content || 'Query blocked by safety guardrail.'}
            </p>
          </div>
        ) : message.isError ? (
          <div className="bg-red-900/20 border border-red-700/30 rounded-xl px-4 py-3">
            <p className="text-red-400 text-sm font-mono leading-relaxed">
              {message.content}
            </p>
          </div>
        ) : (
          <div className="text-sm text-cream leading-relaxed font-mono">
            {html ? (
              <div
                className="prose-research"
                dangerouslySetInnerHTML={{ __html: html }}
              />
            ) : (
              message.isStreaming && !message.progressMessage && (
                <span className="text-cream-600">Thinking</span>
              )
            )}
            {message.isStreaming && <StreamingCursor />}
          </div>
        )}

        {/* Footer: grounded badge + sources button */}
        {!message.isStreaming && !message.isBlocked && !message.isError && message.content && (
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <GroundedBadge grounded={message.grounded} />
            {message.sources.length > 0 && (
              <button
                onClick={onShowSources}
                className="text-xs text-gold hover:text-gold-light font-mono underline underline-offset-2 transition-colors"
              >
                {message.sources.length} source{message.sources.length !== 1 ? 's' : ''} →
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
