/**
 * Thin wrapper around fetch() for talking to the Flask API.
 *
 * - Every call goes to a relative "/api/..." URL. In development the Vite
 *   proxy forwards it to Flask; in production a reverse proxy would do the same.
 * - Successful calls resolve with the parsed JSON (or null for 204 No Content).
 * - Failed calls reject with an ApiError that carries the server's message,
 *   HTTP status and per-field validation details.
 */

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details || {}
  }
}

async function request(path, { method = 'GET', body } = {}) {
  const options = { method, headers: {} }
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`/api${path}`, options)
  } catch {
    // fetch() itself only throws when the network request could not be made.
    throw new ApiError('Could not reach the server. Is the backend running?', 0)
  }

  if (response.status === 204) return null

  let data = null
  try {
    data = await response.json()
  } catch {
    data = null // non-JSON body (should not happen with our API)
  }

  if (!response.ok) {
    const message = (data && data.error) || `Request failed with status ${response.status}`
    throw new ApiError(message, response.status, data && data.details)
  }
  return data
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  delete: (path) => request(path, { method: 'DELETE' }),
}
