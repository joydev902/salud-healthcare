import { Navigate, Route, Routes } from 'react-router'
import LoginPage from '../features/auth/LoginPage'
import { useCurrentUser } from '../features/auth/useAuth'
import ImportsPage from '../features/imports/ImportsPage'
import AppShell from './AppShell'
import RequireAuth from './RequireAuth'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route
          path="imports"
          element={
            <RequireAuth role="ADMIN">
              <ImportsPage />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function HomePage() {
  const { data: user } = useCurrentUser()
  if (!user) return null

  return (
    <main className="page">
      <h1>Work queue</h1>
      {user.providers.length === 0 ? (
        <p className="muted">
          You have no provider assignments yet. Ask an Admin to assign providers to you.
        </p>
      ) : (
        <>
          <p className="muted">You can see opportunities for these providers:</p>
          <ul>
            {user.providers.map((p) => (
              <li key={p.id}>
                {p.name} <span className="muted">· {p.group_name}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  )
}
