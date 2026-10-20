import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import type { UserRole } from '../features/auth/api'
import { useCurrentUser } from '../features/auth/useAuth'

/** UX-only guard; the API enforces authentication and roles on every request. */
export default function RequireAuth({ children, role }: { children: ReactNode; role?: UserRole }) {
  const location = useLocation()
  const me = useCurrentUser()

  if (me.isPending) return <p className="page muted">Loading…</p>
  if (me.isError) return <p className="page form-error">Unable to reach the server.</p>
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (role && me.data.role !== role) return <Navigate to="/" replace />
  return children
}
