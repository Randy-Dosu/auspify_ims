import { useState } from 'react'
import { api } from '../api/client'
import StockBadge from './StockBadge'

/**
 * One form for all three stock operations.
 *
 * Props
 *   mode        'in' | 'out' | 'adjust'
 *   products    [{id, sku, name, quantity_in_stock, stock_status}] for the picker
 *   productId   currently selected product id ('' when none)
 *   onProductChange(id)
 *   onSuccess(result)   called with the API response {transaction, product}
 */
const MODES = {
  in: {
    title: 'Stock In',
    endpoint: '/stock/in',
    quantityLabel: 'Quantity received',
    defaultReason: 'Purchase order',
    button: 'Receive stock',
  },
  out: {
    title: 'Stock Out',
    endpoint: '/stock/out',
    quantityLabel: 'Quantity removed',
    defaultReason: 'Sale',
    button: 'Remove stock',
  },
  adjust: {
    title: 'Adjustment',
    endpoint: '/stock/adjust',
    quantityLabel: 'Counted quantity (new total)',
    defaultReason: 'Stock count correction',
    button: 'Apply adjustment',
  },
}

function StockForm({ mode, products, productId, onProductChange, onSuccess }) {
  const config = MODES[mode]
  const [quantity, setQuantity] = useState('')
  const [reason, setReason] = useState(config.defaultReason)
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState({})
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const selected = products.find((p) => String(p.id) === String(productId))

  async function handleSubmit(event) {
    event.preventDefault()
    setErrors({})
    setError(null)

    // Client-side checks mirror the API rules so most mistakes never leave the browser.
    const found = {}
    if (!productId) found.product_id = 'Choose a product.'
    const qty = Number(quantity)
    if (quantity === '' || !Number.isInteger(qty)) found.quantity = 'Enter a whole number.'
    else if (mode === 'adjust' ? qty < 0 : qty < 1) found.quantity = mode === 'adjust' ? 'Cannot be negative.' : 'Must be at least 1.'
    else if (mode === 'out' && selected && qty > selected.quantity_in_stock) {
      found.quantity = `Only ${selected.quantity_in_stock} in stock.`
    } else if (mode === 'adjust' && selected && qty === selected.quantity_in_stock) {
      found.quantity = 'That is already the current quantity.'
    }
    if (Object.keys(found).length) {
      setErrors(found)
      return
    }

    const payload = {
      product_id: Number(productId),
      reason: reason.trim() || null,
      note: note.trim() || null,
    }
    if (mode === 'adjust') payload.new_quantity = qty
    else payload.quantity = qty

    setBusy(true)
    try {
      const result = await api.post(config.endpoint, payload)
      setQuantity('')
      setNote('')
      onSuccess(result)
    } catch (err) {
      setError(err.message)
      setErrors(err.details || {})
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={handleSubmit} noValidate aria-label={`${config.title} form`}>
      <div className="form-grid">
        <div className="field field-wide">
          <label htmlFor={`${mode}-product`}>Product *</label>
          <select
            id={`${mode}-product`}
            value={productId}
            onChange={(e) => onProductChange(e.target.value)}
          >
            <option value="">— choose a product —</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.sku} — {p.name} ({p.quantity_in_stock} in stock)
              </option>
            ))}
          </select>
          {errors.product_id && <span className="error-text">{errors.product_id}</span>}
          {selected && (
            <span className="hint">
              Current stock: <strong>{selected.quantity_in_stock}</strong> · reorder level{' '}
              {selected.reorder_level} · <StockBadge status={selected.stock_status} />
            </span>
          )}
        </div>

        <div className="field">
          <label htmlFor={`${mode}-quantity`}>{config.quantityLabel} *</label>
          <input
            id={`${mode}-quantity`}
            type="number"
            min={mode === 'adjust' ? 0 : 1}
            step="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
          />
          {errors.quantity && <span className="error-text">{errors.quantity}</span>}
        </div>

        <div className="field">
          <label htmlFor={`${mode}-reason`}>Reason</label>
          <input
            id={`${mode}-reason`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={100}
          />
          {errors.reason && <span className="error-text">{errors.reason}</span>}
        </div>

        <div className="field field-wide">
          <label htmlFor={`${mode}-note`}>Note</label>
          <input
            id={`${mode}-note`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={1000}
            placeholder="Optional reference, e.g. invoice or PO number"
          />
          {errors.note && <span className="error-text">{errors.note}</span>}
        </div>
      </div>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Saving…' : config.button}
        </button>
      </div>
    </form>
  )
}

export default StockForm
