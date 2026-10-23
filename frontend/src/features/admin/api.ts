import { apiFetch } from '../../shared/api/client'
import type { ProviderRef, UserRole } from '../auth/api'

export interface ManagedUser {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  providers: ProviderRef[]
}

export interface UserPage {
  items: ManagedUser[]
  next_cursor: string | null
  has_more: boolean
}

export interface NewUser {
  email: string
  full_name: string
  role: UserRole
  password: string
  provider_ids: number[]
}

export type UserChanges = Partial<{
  full_name: string
  role: UserRole
  is_active: boolean
  password: string
}>

export const MIN_PASSWORD_LENGTH = 12

export const adminApi = {
  users: (q: string, cursor: string | null) => {
    const params = new URLSearchParams({ limit: '50' })
    if (q) params.set('q', q)
    if (cursor) params.set('cursor', cursor)
    return apiFetch<UserPage>(`/admin/users?${params}`)
  },
  create: (body: NewUser) =>
    apiFetch<ManagedUser>('/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  update: (id: string, changes: UserChanges) =>
    apiFetch<ManagedUser>(`/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  setProviders: (id: string, providerIds: number[]) =>
    apiFetch<ProviderRef[]>(`/admin/users/${id}/providers`, {
      method: 'PUT',
      body: JSON.stringify({ provider_ids: providerIds }),
    }),
  providers: () => apiFetch<ProviderRef[]>('/admin/providers'),
}
