import { useState } from 'react'
import { api } from '../api/client'
import ProductForm from '../components/ProductForm'
import ProductTable from '../components/ProductTable'
import { useApi } from '../hooks/useApi'

/**
 * Products page: list + create / edit / delete.
 *
 * Data flow: every successful write calls `reload()` so the table always
 * shows exactly what the server has (no optimistic guessing).
 */
function Products() {
  const products = useApi('/products')
  const categories = useApi('/categories')
  const suppliers = useApi('/suppliers')

  // null = form hidden, 'new' = creating, or a product object = editing
  const [editing, setEditing] = useState(null)
  const [serverErrors, setServerErrors] = useState({})
  const [message, setMessage] = useState(null) // {type: 'success'|'error', text}

  function openCreate() {
    setEditing('new')
    setServerErrors({})
    setMessage(null)
  }

  function openEdit(product) {
    setEditing(product)
    setServerErrors({})
    setMessage(null)
  }

  function closeForm() {
    setEditing(null)
    setServerErrors({})
  }

  async function handleSubmit(payload) {
    setServerErrors({})
    try {
      if (editing === 'new') {
        const created = await api.post('/products', payload)
        setMessage({ type: 'success', text: `Product "${created.name}" created.` })
      } else {
        const updated = await api.put(`/products/${editing.id}`, payload)
        setMessage({ type: 'success', text: `Product "${updated.name}" updated.` })
      }
      closeForm()
      products.reload()
      categories.reload() // product counts changed
      suppliers.reload()
    } catch (err) {
      setServerErrors(err.details || {})
      setMessage({ type: 'error', text: err.message })
    }
  }

  async function handleDelete(product) {
    const ok = window.confirm(
      `Delete "${product.name}" (${product.sku})?\n\nThis also removes its stock history.`,
    )
    if (!ok) return
    try {
      await api.delete(`/products/${product.id}`)
      setMessage({ type: 'success', text: `Product "${product.name}" deleted.` })
      if (editing && editing.id === product.id) closeForm()
      products.reload()
      categories.reload()
      suppliers.reload()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Products</h1>
          {products.data && <p className="muted">{products.data.total} products</p>}
        </div>
        {editing === null && (
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            + Add product
          </button>
        )}
      </div>

      {message && (
        <p className={`alert alert-${message.type}`} role="status">
          {message.text}
        </p>
      )}

      {editing !== null && (
        <ProductForm
          key={editing === 'new' ? 'new' : editing.id} // remount when switching records
          product={editing === 'new' ? null : editing}
          categories={categories.data ? categories.data.items : []}
          suppliers={suppliers.data ? suppliers.data.items : []}
          onSubmit={handleSubmit}
          onCancel={closeForm}
          serverErrors={serverErrors}
        />
      )}

      {products.loading && <p className="muted">Loading products…</p>}
      {products.error && (
        <p className="alert alert-error" role="alert">
          {products.error}
        </p>
      )}
      {products.data && (
        <ProductTable products={products.data.items} onEdit={openEdit} onDelete={handleDelete} />
      )}
    </div>
  )
}

export default Products
