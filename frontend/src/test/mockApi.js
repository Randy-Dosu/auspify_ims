import { vi } from 'vitest'

/**
 * Replace the global fetch() with a fake API for component tests.
 *
 *   mockFetch({
 *     'GET /api/products': { items: [...], total: 1 },
 *     'POST /api/products': { status: 201, body: {...} },
 *   })
 *
 * A route value can be a plain object (=> 200) or {status, body}.
 * Returns the vi.fn() so tests can inspect calls.
 */
export function mockFetch(routes) {
  const fn = vi.fn(async (url, options = {}) => {
    const method = (options.method || 'GET').toUpperCase()
    const path = url.split('?')[0]
    const route = routes[`${method} ${path}`]
    if (route === undefined) {
      return jsonResponse({ error: `No mock for ${method} ${path}` }, 404)
    }
    const value = typeof route === 'function' ? route(options) : route
    if (value && typeof value === 'object' && 'status' in value && 'body' in value) {
      return jsonResponse(value.body, value.status)
    }
    return jsonResponse(value, 200)
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

function jsonResponse(body, status) {
  if (status === 204) return new Response(null, { status })
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Parse the JSON body of the n-th call made with a given method+path. */
export function bodyOfCall(fn, method, path) {
  const call = fn.mock.calls.find(
    ([url, options]) => (options?.method || 'GET') === method && url.split('?')[0] === path,
  )
  return call ? JSON.parse(call[1].body) : undefined
}
