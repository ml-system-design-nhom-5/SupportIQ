export class ApiError extends Error {
  constructor(public status: number, message: string, public traceId?: string, public code?: string) { super(message) }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...options.headers } })
  } catch {
    throw new ApiError(0, 'The connection was interrupted. Check your connection and try again. Your text is kept.')
  }
  if (!response.ok) {
    const problem = await response.json().catch(() => ({})) as Record<string, string>
    if (response.status === 401 && path !== '/v1/sessions' && path !== '/v1/sessions/current') window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(response.status, problem.detail || 'The request could not be completed. Try again.', problem.trace_id || response.headers.get('X-Trace-ID') || undefined, problem.type)
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}

export function post<T>(path: string, body: unknown, key: string = crypto.randomUUID()) {
  return api<T>(path, {method: 'POST', headers: {'Idempotency-Key': key}, body: JSON.stringify(body)})
}
