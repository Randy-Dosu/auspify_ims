import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import StockBadge from '../components/StockBadge'
import StockForm from '../components/StockForm'
import TransactionHistory from '../components/TransactionHistory'
import { useApi } from '../hooks/useApi'

const TABS = [
  { id: 'in', label: 'Stock In' },
  { id: 'out', label: 'Stock Out' },
  { id: 'adjust', label: 'Adjustment' },
]

/**
 * Stock Movements page.
 *  - left: Stock In / Out / Adjustment forms (tabs)
 *  - right: history for the selected product
 *  - bottom: the most recent movements across all products
 *
 * The selected product is kept in the URL (?product=ID) so the Products page
 * can deep-link to a product's history.
 */
function StockMovements() {
  const [searchParams, setSearchParams] = useSearchParams()
  const productId = searchParams.get('product') || ''
  const [mode, setMode] = useState('in')
  const [message, setMessage] = useState(null)
  const [pickerSearch, setPickerSearch] = useState('')

  // The products API is paginated, so the picker loads at most 100 matches
  // (sorted by SKU) and offers a search box to narrow them down.
  const pickerQuery = new URLSearchParams({ per_page: '100', sort: 'sku' })
  if (pickerSearch) pickerQuery.set('search', pickerSearch)
  const products = useApi(`/products?${pickerQuery.toString()}`)
  // The selected product is loaded on its own so a deep link (?product=ID)
  // works even when that product is not in the current picker results.
  const selectedProduct = useApi(productId ? `/products/${productId}` : null)
  const history = useApi(productId ? `/products/${productId}/transactions?limit=100` : null)
  const recent = useApi('/stock/transactions?limit=25')

  const selected = selectedProduct.data
  const pickerItems = products.data ? products.data.items : []
  const productList =
    selected && !pickerItems.some((p) => p.id === selected.id) ? [selected, ...pickerItems] : pickerItems

  function selectProduct(id) {
    setSearchParams(id ? { product: id } : {})
    setMessage(null)
  }

  function handleSuccess(result) {
    const tx = result.transaction
    const verb = tx.type === 'IN' ? 'received' : tx.type === 'OUT' ? 'removed' : 'adjusted by'
    setMessage({
      type: 'success',
      text: `${tx.sku}: ${verb} ${tx.quantity} — now ${result.product.quantity_in_stock} in stock.`,
    })
    // Refresh everything that shows quantities or history.
    products.reload()
    selectedProduct.reload()
    history.reload()
    recent.reload()
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Stock Movements</h1>
      </div>

      {(products.error || selectedProduct.error) && (
        <p className="alert alert-error" role="alert">
          {products.error || selectedProduct.error}
        </p>
      )}

      <div className="two-col">
        <section className="card">
          <div className="tabs" role="tablist" aria-label="Stock operation">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={mode === tab.id}
                className={`tab ${mode === tab.id ? 'active' : ''}`}
                onClick={() => {
                  setMode(tab.id)
                  setMessage(null)
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {message && (
            <p className={`alert alert-${message.type}`} role="status">
              {message.text}
            </p>
          )}

          <StockForm
            key={mode} // remount so each tab starts with its own defaults
            mode={mode}
            products={productList}
            productId={productId}
            onProductChange={selectProduct}
            onSuccess={handleSuccess}
            search={pickerSearch}
            onSearchChange={setPickerSearch}
            totalMatches={products.data ? products.data.total : 0}
            matchesShown={pickerItems.length}
          />
        </section>

        <section className="card">
          <h2>
            History{' '}
            {selected && (
              <span className="muted">
                — {selected.sku} · {selected.name} <StockBadge status={selected.stock_status} />
              </span>
            )}
          </h2>
          {!productId && <p className="empty-state">Choose a product to see its movement history.</p>}
          {productId && history.loading && <p className="muted">Loading history…</p>}
          {productId && history.error && (
            <p className="alert alert-error" role="alert">
              {history.error}
            </p>
          )}
          {productId && history.data && <TransactionHistory transactions={history.data.items} />}
        </section>
      </div>

      <section className="card">
        <h2>Recent movements (all products)</h2>
        {recent.data && <TransactionHistory transactions={recent.data.items} showProduct />}
      </section>
    </div>
  )
}

export default StockMovements
