import { apiFetch } from './client'
import type { Chat } from '../types'

interface CreateChatResponse extends Chat {
  user_id: string
  updated_at: string
}

export function createChat(userId: string, title?: string): Promise<CreateChatResponse> {
  return apiFetch('/chats', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, chat_title: title ?? null }),
  })
}

export function getChat(chatId: string): Promise<CreateChatResponse> {
  return apiFetch(`/chats/${chatId}`)
}
