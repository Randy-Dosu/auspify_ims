import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'

/**
 * Load JSON from the API and keep it in component state.
 *
 *   const { data, loading, error, reload } = useApi('/products')
 *
 * - Re-fetches automatically whenever `path` changes.
 * - `reload()` re-fetches the same path (call it after a create/update/delete).
 * - Pass `null` as the path to skip fetching.
 *
 * Each request is identified by a key (path + reload counter). `loading` is
 * derived from "has the result for the current key arrived yet?", which keeps
 * the previous data on screen while a refresh is in flight (no flicker) and
 * avoids setting state synchronously inside the effect.
 */
export function useApi(path) {
  const [version, setVersion] = useState(0) // bumping this triggers a reload
  const [result, setResult] = useState({ key: null, data: null, error: null })

  const key = path ? `${path}#${version}` : null

  useEffect(() => {
    if (!key) return undefined
    let cancelled = false // ignore the result if the component unmounted or the path changed
    api
      .get(path)
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: null })
      })
      .catch((err) => {
        if (!cancelled) setResult({ key, data: null, error: err.message })
      })
    return () => {
      cancelled = true
    }
  }, [key, path])

  const reload = useCallback(() => setVersion((v) => v + 1), [])

  const loading = Boolean(key) && result.key !== key
  return {
    data: result.data,
    error: loading ? null : result.error,
    loading,
    reload,
  }
}
