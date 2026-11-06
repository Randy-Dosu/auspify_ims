import { useState } from 'react'

/**
 * Generic "simple list" manager used for both categories and suppliers.
 *
 * Props
 *   title      heading, e.g. "Categories"
 *   items      rows from the API (must have `id` and `product_count`)
 *   fields     [{ name, label, required?, type? }] - columns/inputs to show
 *   onCreate   async (values) => void
 *   onUpdate   async (id, values) => void
 *   onDelete   async (item) => void
 */
function emptyValues(fields) {
  return Object.fromEntries(fields.map((f) => [f.name, '']))
}

function LookupManager({ title, items, fields, onCreate, onUpdate, onDelete }) {
  const [values, setValues] = useState(() => emptyValues(fields))
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [busy, setBusy] = useState(false)

  function startEdit(item) {
    setEditingId(item.id)
    setValues(Object.fromEntries(fields.map((f) => [f.name, item[f.name] ?? ''])))
    setError(null)
    setFieldErrors({})
  }

  function reset() {
    setEditingId(null)
    setValues(emptyValues(fields))
    setError(null)
    setFieldErrors({})
  }

  async function handleSubmit(event) {
    event.preventDefault()
    // Empty optional fields are sent as null so the API clears them.
    const payload = Object.fromEntries(
      fields.map((f) => [f.name, values[f.name].trim() === '' ? null : values[f.name].trim()]),
    )
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      if (editingId === null) {
        await onCreate(payload)
      } else {
        await onUpdate(editingId, payload)
      }
      reset()
    } catch (err) {
      setError(err.message)
      setFieldErrors(err.details || {})
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(item) {
    const label = item.name || `#${item.id}`
    if (!window.confirm(`Delete "${label}"?`)) return
    setError(null)
    try {
      await onDelete(item)
      if (editingId === item.id) reset()
    } catch (err) {
      setError(err.message)
    }
  }

  const formId = `${title.toLowerCase().replace(/\s+/g, '-')}-form`

  return (
    <section className="card">
      <h2>{title}</h2>

      <form className="inline-form" onSubmit={handleSubmit} noValidate aria-label={`${title} form`}>
        {fields.map((field) => (
          <div className="field" key={field.name}>
            <label htmlFor={`${formId}-${field.name}`}>
              {field.label}
              {field.required ? ' *' : ''}
            </label>
            <input
              id={`${formId}-${field.name}`}
              type={field.type || 'text'}
              value={values[field.name]}
              onChange={(e) => setValues((prev) => ({ ...prev, [field.name]: e.target.value }))}
              maxLength={field.maxLength || 100}
              required={field.required}
            />
            {fieldErrors[field.name] && <span className="error-text">{fieldErrors[field.name]}</span>}
          </div>
        ))}
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {editingId === null ? 'Add' : 'Save'}
          </button>
          {editingId !== null && (
            <button type="button" className="btn" onClick={reset} disabled={busy}>
              Cancel
            </button>
          )}
        </div>
      </form>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      {items.length === 0 ? (
        <p className="empty-state">Nothing here yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {fields.map((f) => (
                  <th key={f.name}>{f.label}</th>
                ))}
                <th className="num">Products</th>
                <th className="actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className={item.id === editingId ? 'row-editing' : ''}>
                  {fields.map((f) => (
                    <td key={f.name}>{item[f.name] || <span className="muted">—</span>}</td>
                  ))}
                  <td className="num">{item.product_count}</td>
                  <td className="actions">
                    <button type="button" className="btn btn-small" onClick={() => startEdit(item)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => handleDelete(item)}
                      disabled={item.product_count > 0}
                      title={
                        item.product_count > 0
                          ? 'Still used by products - reassign them first'
                          : 'Delete'
                      }
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default LookupManager
