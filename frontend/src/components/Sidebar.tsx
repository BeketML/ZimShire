import type { Chat } from '../types'
import HealthStatus from './HealthStatus'

interface Props {
  chats: Chat[]
  activeChatId: string | null
  onSelect: (chatId: string) => void
  onNew: () => void
  isStreaming: boolean
}

export default function Sidebar({ chats, activeChatId, onSelect, onNew, isStreaming }: Props) {
  return (
    <aside className="w-60 flex-shrink-0 bg-navy-800 border-r border-navy-700 flex flex-col">
      {/* Header */}
      <div className="px-4 pt-5 pb-4 border-b border-navy-700">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded bg-navy-700 border border-gold/30 flex items-center justify-center">
            <span className="font-display text-xs font-bold text-gold">Z</span>
          </div>
          <span className="font-display font-semibold text-cream text-sm">ZimShire</span>
        </div>
        <button
          onClick={onNew}
          disabled={isStreaming}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-gold/30 text-gold hover:bg-navy-700 hover:border-gold/60 transition-all text-sm font-mono disabled:opacity-40"
        >
          <span className="text-base leading-none">+</span>
          <span>New research</span>
        </button>
      </div>

      {/* Chat list */}
      <div className="flex-1 overflow-y-auto py-2">
        {chats.length === 0 ? (
          <p className="px-4 py-3 text-xs text-cream-600 font-mono">No chats yet</p>
        ) : (
          chats.map((chat) => (
            <button
              key={chat.chat_id}
              onClick={() => onSelect(chat.chat_id)}
              className={`w-full text-left px-4 py-2.5 text-xs font-mono transition-colors truncate ${
                chat.chat_id === activeChatId
                  ? 'bg-navy-700 text-cream border-l-2 border-gold'
                  : 'text-cream-600 hover:bg-navy-700/50 hover:text-cream border-l-2 border-transparent'
              }`}
            >
              {chat.chat_title || 'Untitled research'}
            </button>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-navy-700">
        <HealthStatus />
      </div>
    </aside>
  )
}
