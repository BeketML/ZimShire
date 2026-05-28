import { useState, useCallback, useRef } from 'react'
import { createChat } from '../api/chats'
import { getMessages, streamMessage } from '../api/messages'
import type { Message, Chat, Source } from '../types'

const CHATS_KEY = 'zimshire_chats'
const ACTIVE_KEY = 'zimshire_active_chat'

function loadChats(): Chat[] {
  try {
    return JSON.parse(localStorage.getItem(CHATS_KEY) ?? '[]')
  } catch {
    return []
  }
}

function saveChats(chats: Chat[]) {
  localStorage.setItem(CHATS_KEY, JSON.stringify(chats))
}

let msgCounter = 0
function localId() {
  return `local-${++msgCounter}`
}

export function useChat(userId: string | null) {
  const [chats, setChats] = useState<Chat[]>(loadChats)
  const [activeChatId, setActiveChatId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_KEY),
  )
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const updateLastAssistant = useCallback((updater: (m: Message) => Message) => {
    setMessages((prev) => {
      const idx = [...prev].reverse().findIndex((m) => m.role === 'assistant')
      if (idx === -1) return prev
      const realIdx = prev.length - 1 - idx
      return prev.map((m, i) => (i === realIdx ? updater(m) : m))
    })
  }, [])

  const selectChat = useCallback(
    async (chatId: string) => {
      if (!userId) return
      setActiveChatId(chatId)
      localStorage.setItem(ACTIVE_KEY, chatId)
      const apiMessages = await getMessages(chatId, userId)
      setMessages(
        apiMessages.map((m) => ({
          id: m.message_id,
          role: m.role,
          content: m.content,
          grounded: m.grounded,
          sources: m.sources ?? [],
          langfuse_trace_id: m.langfuse_trace_id ?? undefined,
          created_at: m.created_at,
          isStreaming: false,
          progressMessage: null,
          isBlocked: false,
          isError: false,
        })),
      )
    },
    [userId],
  )

  const newChat = useCallback(
    async (title?: string) => {
      if (!userId) return null
      const chat = await createChat(userId, title)
      const newEntry: Chat = {
        chat_id: chat.chat_id,
        chat_title: chat.chat_title,
        model: chat.model,
        created_at: chat.created_at,
      }
      setChats((prev) => {
        const updated = [newEntry, ...prev]
        saveChats(updated)
        return updated
      })
      setActiveChatId(chat.chat_id)
      localStorage.setItem(ACTIVE_KEY, chat.chat_id)
      setMessages([])
      return chat.chat_id
    },
    [userId],
  )

  const sendMessage = useCallback(
    async (query: string, chatIdOverride?: string) => {
      if (!userId || isStreaming) return
      let chatId = chatIdOverride ?? activeChatId
      if (!chatId) {
        chatId = await newChat(query.slice(0, 60)) ?? null
        if (!chatId) return
      }

      // Append human message
      const humanId = localId()
      setMessages((prev) => [
        ...prev,
        {
          id: humanId,
          role: 'human',
          content: query,
          grounded: null,
          sources: [],
          created_at: new Date().toISOString(),
          isStreaming: false,
          progressMessage: null,
          isBlocked: false,
          isError: false,
        },
      ])

      // Append empty assistant placeholder
      const assistantId = localId()
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          grounded: null,
          sources: [],
          created_at: new Date().toISOString(),
          isStreaming: true,
          progressMessage: null,
          isBlocked: false,
          isError: false,
        },
      ])

      setIsStreaming(true)
      abortRef.current = new AbortController()

      try {
        await streamMessage(chatId, userId, query, {
          onProgress: (_stage, message) => {
            updateLastAssistant((m) => ({ ...m, progressMessage: message }))
          },
          onToken: (content) => {
            updateLastAssistant((m) => ({ ...m, content: m.content + content, progressMessage: null }))
          },
          onReplace: (content) => {
            updateLastAssistant((m) => ({ ...m, content, progressMessage: null }))
          },
          onBlocked: (reason) => {
            updateLastAssistant((m) => ({
              ...m,
              content: reason,
              isBlocked: true,
              isStreaming: false,
              progressMessage: null,
            }))
          },
          onDone: (grounded: boolean | null, sources: Source[], messageId: string | null) => {
            updateLastAssistant((m) => ({
              ...m,
              id: messageId ?? m.id,
              grounded,
              sources,
              isStreaming: false,
              progressMessage: null,
            }))
          },
          onError: (detail) => {
            updateLastAssistant((m) => ({
              ...m,
              content: `Error: ${detail}`,
              isError: true,
              isStreaming: false,
              progressMessage: null,
            }))
          },
        }, abortRef.current.signal)
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== 'AbortError') {
          updateLastAssistant((m) => ({
            ...m,
            content: 'Connection lost. Please try again.',
            isError: true,
            isStreaming: false,
            progressMessage: null,
          }))
        }
      } finally {
        setIsStreaming(false)
      }
    },
    [userId, isStreaming, activeChatId, newChat, updateLastAssistant],
  )

  const stopStream = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return {
    chats,
    activeChatId,
    messages,
    isStreaming,
    selectChat,
    newChat,
    sendMessage,
    stopStream,
  }
}
