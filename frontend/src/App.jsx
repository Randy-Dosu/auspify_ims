import { useEffect, useState } from 'react'
import './App.css'

/**
 * Step 0: the only job of this component is to prove the wiring works.
 * On first render it calls GET /api/health (proxied by Vite to Flask)
 * and shows the result, so we can see end-to-end connectivity in the browser.
 */
function App() {
  // Three possible UI states: loading -> ok | error
  const [health, setHealth] = useState(null) // JSON returned by the backend
  const [error, setError] = useState(null) // error message, if the call fails
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Relative URL: the Vite dev server forwards /api/* to Flask.
    fetch('/api/health')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend responded with HTTP ${response.status}`)
        }
        return response.json()
      })
      .then((data) => setHealth(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, []) // empty dependency array = run once, after the first render

  return (
    <main className="app">
      <h1>Auspify IMS</h1>
      <p className="subtitle">Inventory Management System</p>

      <section className="status-card">
        <h2>Backend connection</h2>

        {loading && <p className="status status-loading">Checking backend…</p>}

        {!loading && error && (
          <p className="status status-error">
            Could not reach the backend: {error}
          </p>
        )}

        {!loading && health && (
          <p className="status status-ok">
            Backend status: <strong>{health.status}</strong> ({health.service})
          </p>
        )}
      </section>
    </main>
  )
}

export default App
