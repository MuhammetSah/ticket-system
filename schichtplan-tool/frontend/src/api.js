const API_URL = import.meta.env.VITE_API_URL

/** Thrown when the API rejects a request because nobody is signed in. */
export class UnauthorizedError extends Error {}

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    // Sends the session cookie; without it every guarded route answers 401.
    credentials: 'include',
    ...options,
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data?.message || `Request failed (${response.status})`
    if (response.status === 401) {
      const error = new UnauthorizedError(message)
      error.data = data
      throw error
    }
    throw new Error(message)
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => request(path, { method: 'DELETE' }),
}

export const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
export const WEEKDAY_NAMES = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
export const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
]
