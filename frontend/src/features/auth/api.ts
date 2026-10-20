import { ApiError, apiFetch } from '../../shared/api/client'

export type UserRole = 'ADMIN' | 'CODER'

export interface ProviderRef {
  id: number
  name: string
  group_name: string
}

export interface CurrentUser {
  id: string
  email: string
  full_name: string
  role: UserRole
  providers: ProviderRef[]
}

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<CurrentUser>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () => apiFetch<void>('/auth/logout', { method: 'POST' }),

  me: async (): Promise<CurrentUser | null> => {
    try {
      return await apiFetch<CurrentUser>('/auth/me')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return null
      throw err
    }
  },
}
