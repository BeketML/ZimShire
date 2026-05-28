import { apiFetch } from './client'

export interface UserResponse {
  user_id: string
  name: string | null
  surname: string | null
  created_at: string
}

export function createUser(name?: string, surname?: string): Promise<UserResponse> {
  return apiFetch('/users', {
    method: 'POST',
    body: JSON.stringify({ name: name ?? null, surname: surname ?? null }),
  })
}
