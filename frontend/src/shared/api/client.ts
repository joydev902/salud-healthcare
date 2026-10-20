export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  requestId: string | null

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    requestId: string | null = null,
  ) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

const API_BASE = '/api/v1'

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  // Custom header required by the backend CSRF check for cookie-authenticated writes.
  headers.set('X-Requested-With', 'fetch')
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'same-origin' })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const err = body?.error
    throw new ApiError(
      res.status,
      err?.code ?? 'HTTP_ERROR',
      err?.message ?? res.statusText,
      err?.details,
      err?.request_id ?? res.headers.get('X-Request-ID'),
    )
  }
  return res.status === 204 ? (undefined as T) : res.json()
}
