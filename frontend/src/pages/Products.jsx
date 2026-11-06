import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import Pagination from '../components/Pagination'
import ProductFilters from '../components/ProductFilters'
import ProductForm from '../components/ProductForm'
import ProductTable from '../components/ProductTable'
import { useApi } from '../hooks/useApi'

/**
 * Products page: searchable, filterable, sortable, paginated list with
 * create / edit / delete.
 *
 * All query state (filters, sort, page) lives in the URL search params, so
 *   - the browser back button works,
 *   - a filtered view can be bookmarked or linked to (e.g. the dashboard's
 *     "Low stock" card links to /products?stock_status=low).
 */
const FILTER_KEYS = ['search', 'category', 'supplier', 'stock_status', 'min_price', 'max_price']
const DEFAULTS = { sort: 'name', order: 'asc', page: '1', per_page: '20' }

function Products() {
  const [searchParams, setSearchParams] = useSearchParams()

  const filters = Object.fromEntries(FILTER_KEYS.map((key) => [key, searchParams.get(key) || '']))
  const sort = searchParams.get('sort') || DEFAULTS.sort
  const order = searchParams.get('order') || DEFAULTS.order
  const page = Number(searchParams.get('page') || DEFAULTS.page)
  const perPage = Number(searchParams.get('per_page') || DEFAULTS.per_page)

  // Build the API query from the URL state, leaving out empty values.
  const query = new URLSearchParams()
  FILTER_KEYS.forEach((key) => filters[key] !== '' && query.set(key, filters[key]))
  query.set('sort', sort)
  query.set('order', order)
  query.set('page', String(page))
  query.set('per_page', String(perPage))

  const products = useApi(`/products?${query.toString()}`)
  const categories = useApi('/categories')
  const suppliers = useApi('/suppliers')

  // null = form hidden, 'new' = creating, or a product object = editing
  const [editing, setEditing] = useState(null)
  const [serverErrors, setServerErrors] = useState({})
  const [message, setMessage] = useState(null) // {type: 'success'|'error', text}

  /** Merge changes into the URL params; any change except page resets to page 1. */
  function updateParams(changes) {
    const next = new URLSearchParams(searchParams)
    Object.entries(changes).forEach(([key, value]) => {
      if (value === '' || value === null || value === undefined || value === DEFAULTS[key]) {
        next.delete(key)
      } else {
        next.set(key, String(value))
      }
    })
    if (!('page' in changes)) next.delete('page')
    setSearchParams(next)
  }

  function handleSort(column) {
    const nextOrder = sort === column && order === 'asc' ? 'desc' : 'asc'
    updateParams({ sort: column, order: nextOrder })
  }

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

  function refreshAll() {
    products.reload()
    categories.reload() // product counts changed
    suppliers.reload()
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
      refreshAll()
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
      refreshAll()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    }
  }

  const hasFilters = FILTER_KEYS.some((key) => filters[key] !== '')
  const data = products.data

  return (
    <div className="page">
      <div className="page-header">
        <h1>Products</h1>
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

      <ProductFilters
        filters={filters}
        categories={categories.data ? categories.data.items : []}
        suppliers={suppliers.data ? suppliers.data.items : []}
        onChange={updateParams}
        onClear={() => updateParams(Object.fromEntries(FILTER_KEYS.map((key) => [key, ''])))}
      />

      {products.error && (
        <p className="alert alert-error" role="alert">
          {products.error}
        </p>
      )}

      {data && (
        <p className="results-count" role="status" aria-live="polite">
          <strong>{data.total}</strong> {data.total === 1 ? 'product' : 'products'}
          {hasFilters ? (data.total === 1 ? ' matches your filters' : ' match your filters') : ''}
          {products.loading ? ' · refreshing…' : ''}
        </p>
      )}

      {data && (
        <ProductTable
          products={data.items}
          onEdit={openEdit}
          onDelete={handleDelete}
          sort={sort}
          order={order}
          onSort={handleSort}
          emptyMessage={
            hasFilters ? 'No products match these filters. Try clearing some of them.' : 'No products yet.'
          }
        />
      )}

      {data && data.total > 0 && (
        <Pagination
          page={data.page}
          perPage={data.per_page}
          total={data.total}
          totalPages={data.total_pages}
          onPageChange={(p) => updateParams({ page: p })}
          onPerPageChange={(n) => updateParams({ per_page: n })}
        />
      )}
    </div>
  )
}

export default Products
