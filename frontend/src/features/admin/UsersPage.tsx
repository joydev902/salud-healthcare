import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import type { ProviderRef, UserRole } from '../auth/api'
import { meQueryKey, useCurrentUser } from '../auth/useAuth'
import { adminApi, MIN_PASSWORD_LENGTH, type ManagedUser, type UserChanges } from './api'
import ProviderPicker from './ProviderPicker'

type Panel = { kind: 'none' } | { kind: 'create' } | { kind: 'edit'; id: string }

export default function UsersPage() {
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [panel, setPanel] = useState<Panel>({ kind: 'none' })

  const users = useInfiniteQuery({
    queryKey: ['admin', 'users', query],
    queryFn: ({ pageParam }) => adminApi.users(query, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const providers = useQuery({ queryKey: ['admin', 'providers'], queryFn: adminApi.providers })

  const rows = users.data?.pages.flatMap((p) => p.items) ?? []
  const editing = panel.kind === 'edit' ? rows.find((u) => u.id === panel.id) : undefined

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    setQuery(search.trim())
  }

  return (
    <main className="page stack">
      <div className="section-header">
        <h1>Users &amp; access</h1>
        <button type="button" onClick={() => setPanel({ kind: 'create' })}>
          New user
        </button>
      </div>

      <div className="split">
        <section className="card">
          <form className="filter-search" onSubmit={onSearch}>
            <input
              type="search"
              placeholder="Search name or email"
              value={search}
              maxLength={100}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button type="submit" className="secondary">
              Search
            </button>
          </form>
          {users.isPending ? (
            <p className="muted">Loading…</p>
          ) : users.isError ? (
            <p className="form-error">Could not load users.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Providers</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr
                    key={u.id}
                    className={editing?.id === u.id ? 'clickable selected' : 'clickable'}
                    onClick={() => setPanel({ kind: 'edit', id: u.id })}
                  >
                    <td>
                      {u.full_name}
                      <div className="muted">{u.email}</div>
                    </td>
                    <td>
                      <span className="badge">{u.role}</span>
                    </td>
                    <td>
                      {u.is_active ? (
                        <span className="badge status-completed">Active</span>
                      ) : (
                        <span className="badge status-failed">Deactivated</span>
                      )}
                    </td>
                    <td>
                      {u.role === 'ADMIN' ? (
                        'All providers'
                      ) : u.providers.length === 0 ? (
                        <span className="muted">None</span>
                      ) : (
                        u.providers.map((p) => p.name).join(', ')
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {users.hasNextPage && (
            <button
              type="button"
              className="secondary load-more"
              onClick={() => users.fetchNextPage()}
              disabled={users.isFetchingNextPage}
            >
              {users.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </button>
          )}
        </section>

        <aside className="card side-panel">
          {panel.kind === 'create' ? (
            <CreateUserForm
              providers={providers.data ?? []}
              onCreated={(u) => setPanel({ kind: 'edit', id: u.id })}
              onCancel={() => setPanel({ kind: 'none' })}
            />
          ) : editing ? (
            <UserEditor key={editing.id} user={editing} providers={providers.data ?? []} />
          ) : (
            <p className="muted">
              Select a user to change their role, access or provider assignments.
            </p>
          )}
        </aside>
      </div>
    </main>
  )
}

function ErrorMessage({ error }: { error: Error | null }) {
  if (!error) return null
  return (
    <p className="form-error" role="alert">
      {error instanceof ApiError ? error.message : 'Something went wrong.'}
    </p>
  )
}

function CreateUserForm({
  providers,
  onCreated,
  onCancel,
}: {
  providers: ProviderRef[]
  onCreated: (user: ManagedUser) => void
  onCancel: () => void
}) {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<UserRole>('CODER')
  const [password, setPassword] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const create = useMutation({
    mutationFn: () =>
      adminApi.create({
        email,
        full_name: fullName,
        role,
        password,
        provider_ids: role === 'ADMIN' ? [] : [...selected],
      }),
    onSuccess: async (user) => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      onCreated(user)
    },
  })

  const valid = email.includes('@') && fullName.trim() && password.length >= MIN_PASSWORD_LENGTH

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) create.mutate()
      }}
    >
      <h2>New user</h2>
      <label>
        Full name
        <input value={fullName} maxLength={200} onChange={(e) => setFullName(e.target.value)} />
      </label>
      <label>
        Email
        <input
          type="email"
          value={email}
          maxLength={320}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      <RoleSelect value={role} onChange={setRole} />
      <label>
        Initial password
        <input
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <span className="muted hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
      </label>
      {role === 'ADMIN' ? (
        <p className="muted">Admins see every provider imported from a file.</p>
      ) : (
        <ProviderPicker providers={providers} selected={selected} onChange={setSelected} />
      )}
      <ErrorMessage error={create.error} />
      <div className="actions">
        <button type="submit" disabled={!valid || create.isPending}>
          {create.isPending ? 'Creating…' : 'Create user'}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function RoleSelect({ value, onChange }: { value: UserRole; onChange: (r: UserRole) => void }) {
  return (
    <label>
      Role
      <select value={value} onChange={(e) => onChange(e.target.value as UserRole)}>
        <option value="CODER">Coder</option>
        <option value="ADMIN">Admin</option>
      </select>
    </label>
  )
}

function UserEditor({ user, providers }: { user: ManagedUser; providers: ProviderRef[] }) {
  const queryClient = useQueryClient()
  const { data: me } = useCurrentUser()
  const isSelf = me?.id === user.id
  const [fullName, setFullName] = useState(user.full_name)
  const [role, setRole] = useState<UserRole>(user.role)
  const [isActive, setIsActive] = useState(user.is_active)
  const [password, setPassword] = useState('')
  const [selected, setSelected] = useState(() => new Set(user.providers.map((p) => p.id)))
  const [saved, setSaved] = useState(false)

  const original = new Set(user.providers.map((p) => p.id))
  const providersChanged =
    role === 'CODER' &&
    (selected.size !== original.size || [...selected].some((id) => !original.has(id)))
  const changes: UserChanges = {
    ...(fullName.trim() !== user.full_name && { full_name: fullName.trim() }),
    ...(role !== user.role && { role }),
    ...(isActive !== user.is_active && { is_active: isActive }),
    ...(password && { password }),
  }
  const dirty = Object.keys(changes).length > 0 || providersChanged
  const passwordOk = !password || password.length >= MIN_PASSWORD_LENGTH

  const save = useMutation({
    mutationFn: async () => {
      if (Object.keys(changes).length > 0) await adminApi.update(user.id, changes)
      if (providersChanged) await adminApi.setProviders(user.id, [...selected])
    },
    onSuccess: () => {
      setPassword('')
      setSaved(true)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      if (isSelf) {
        // Own scope may have changed: refresh identity and every provider-scoped view.
        for (const key of [meQueryKey, ['ref'], ['members'], ['member'], ['opportunity']]) {
          queryClient.invalidateQueries({ queryKey: key })
        }
      }
    },
  })

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        setSaved(false)
        if (dirty && passwordOk) save.mutate()
      }}
    >
      <div>
        <h2>{user.full_name}</h2>
        <span className="muted">{user.email}</span>
      </div>
      <label>
        Full name
        <input value={fullName} maxLength={200} onChange={(e) => setFullName(e.target.value)} />
      </label>
      {isSelf ? (
        <p className="muted">You cannot change your own role or deactivate yourself.</p>
      ) : (
        <>
          <RoleSelect value={role} onChange={setRole} />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            Account active (unchecking signs the user out on their next request)
          </label>
        </>
      )}
      <label>
        Reset password
        <input
          type="password"
          autoComplete="new-password"
          placeholder="Leave blank to keep the current password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {!passwordOk && (
          <span className="form-error hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
        )}
      </label>
      {role === 'ADMIN' ? (
        <p className="muted">Admins see every provider imported from a file.</p>
      ) : (
        <ProviderPicker providers={providers} selected={selected} onChange={setSelected} />
      )}
      <ErrorMessage error={save.error} />
      {saved && !save.error && !dirty && <p className="success">Changes saved.</p>}
      <div className="actions">
        <button type="submit" disabled={!dirty || !passwordOk || save.isPending}>
          {save.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  )
}
