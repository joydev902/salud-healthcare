import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'
import { ApiError } from '../../shared/api/client'
import { useCurrentUser, useLogin } from './useAuth'

const DEMO_ACCOUNTS = [
  { email: 'admin@salud.test', label: 'Admin — all providers' },
  { email: 'coder.one@salud.test', label: 'Coder' },
  { email: 'coder.two@salud.test', label: 'Coder' },
]

export default function LoginPage() {
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  const me = useCurrentUser()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  if (me.data) return <Navigate to={from} replace />

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate({ email: email.trim(), password })
  }

  const error =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? 'Unable to reach the server'
        : null

  return (
    <main className="login">
      <form className="card login-card" onSubmit={onSubmit} noValidate>
        <h1>Salud MRA</h1>
        <p className="muted">Sign in to the coding opportunity work queue</p>

        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" disabled={login.isPending || !email || !password}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>

        {import.meta.env.DEV && (
          <details className="demo-accounts">
            <summary>Demo accounts (synthetic data)</summary>
            <ul>
              {DEMO_ACCOUNTS.map((a) => (
                <li key={a.email}>
                  <button type="button" className="link" onClick={() => setEmail(a.email)}>
                    {a.email}
                  </button>{' '}
                  <span className="muted">{a.label}</span>
                </li>
              ))}
            </ul>
            <p className="muted">
              Password: <code>Password123!</code>
            </p>
          </details>
        )}
      </form>
    </main>
  )
}
