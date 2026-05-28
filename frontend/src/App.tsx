import { useUser } from './hooks/useUser'
import { useChat } from './hooks/useChat'
import Sidebar from './components/Sidebar'
import ChatThread from './components/ChatThread'

export default function App() {
  const { userId, loading } = useUser()
  const { chats, activeChatId, messages, isStreaming, selectChat, newChat, sendMessage, stopStream } =
    useChat(userId)

  if (loading || !userId) {
    return (
      <div className="h-full flex items-center justify-center bg-navy">
        <div className="text-center">
          <div className="font-display text-2xl font-bold text-gold mb-2">ZimShire</div>
          <div className="flex gap-1 justify-center">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="w-1.5 h-1.5 bg-gold rounded-full animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex bg-navy">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelect={selectChat}
        onNew={() => newChat()}
        isStreaming={isStreaming}
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        <ChatThread
          messages={messages}
          isStreaming={isStreaming}
          onSend={sendMessage}
          onStop={stopStream}
        />
      </div>
    </div>
  )
}
