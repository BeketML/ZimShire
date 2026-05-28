import { useState, useEffect } from 'react'
import { createUser } from '../api/users'

const KEY = 'zimshire_user_id'

export function useUser() {
  const [userId, setUserId] = useState<string | null>(() => localStorage.getItem(KEY))
  const [loading, setLoading] = useState(!localStorage.getItem(KEY))

  useEffect(() => {
    if (userId) return
    createUser()
      .then((u) => {
        localStorage.setItem(KEY, u.user_id)
        setUserId(u.user_id)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [userId])

  return { userId, loading }
}
