import { useEffect, useRef, useState } from 'react'
import type { Message, Source } from '../types'
import MessageBubble from './MessageBubble'
import QueryInput from './QueryInput'
import EmptyState from './EmptyState'
import SourcesPanel from './SourcesPanel'

interface Props {
  messages: Message[]
  isStreaming: boolean
  onSend: (query: string) => void
  onStop: () => void
}

export default function ChatThread({ messages, isStreaming, onSend, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [activeSources, setActiveSources] = useState<Source[] | null>(null)

  // Scroll to bottom on new messages / tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const isEmpty = messages.length === 0

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Main thread */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          {isEmpty ? (
            <EmptyState onSelect={onSend} />
          ) : (
            <div className="max-w-3xl mx-auto px-6 pt-8 pb-4">
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onShowSources={() => setActiveSources(msg.sources)}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <QueryInput onSend={onSend} disabled={isStreaming} onStop={onStop} />
      </div>

      {/* Sources panel */}
      {activeSources && activeSources.length > 0 && (
        <SourcesPanel sources={activeSources} onClose={() => setActiveSources(null)} />
      )}
    </div>
  )
}
