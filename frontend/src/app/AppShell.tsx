import { NavLink, Outlet, useNavigate } from 'react-router'
import { useCurrentUser, useLogout } from '../features/auth/useAuth'

export default function AppShell() {
  const { data: user } = useCurrentUser()
  const logout = useLogout()
  const navigate = useNavigate()

  const onLogout = () => logout.mutate(undefined, { onSettled: () => navigate('/login') })

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Salud MRA</span>
        <nav>
          <NavLink to="/queue">Work queue</NavLink>
          {user?.role === 'ADMIN' && <NavLink to="/imports">Imports</NavLink>}
          {user?.role === 'ADMIN' && <NavLink to="/admin/users">Users</NavLink>}
        </nav>
        <div className="user">
          <span>
            {user?.full_name} <span className="badge">{user?.role}</span>
          </span>
          <button type="button" className="secondary" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
