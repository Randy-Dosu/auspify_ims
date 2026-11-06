import { useState } from 'react'

/**
 * Create / edit form for a product.
 *
 * Props
 *   product     existing product to edit, or null to create a new one
 *   categories  [{id, name}] for the category dropdown
 *   suppliers   [{id, name}] for the supplier dropdown
 *   onSubmit    async (values) => void   - called with a clean JSON payload
 *   onCancel    () => void
 *   serverErrors  {field: message} returned by the API (shown under fields)
 */
const EMPTY = {
  sku: '',
  name: '',
  description: '',
  category_id: '',
  supplier_id: '',
  unit_price: '',
  quantity_in_stock: '0',
  reorder_level: '10',
}

function toFormValues(product) {
  if (!product) return EMPTY
  return {
    sku: product.sku ?? '',
    name: product.name ?? '',
    description: product.description ?? '',
    category_id: product.category_id ?? '',
    supplier_id: product.supplier_id ?? '',
    unit_price: product.unit_price ?? '',
    quantity_in_stock: String(product.quantity_in_stock ?? 0),
    reorder_level: String(product.reorder_level ?? 10),
  }
}

function ProductForm({ product, categories, suppliers, onSubmit, onCancel, serverErrors = {} }) {
  const isEdit = Boolean(product)
  const [values, setValues] = useState(() => toFormValues(product))
  const [localErrors, setLocalErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)

  // Server-side messages win over local ones for the same field.
  const errors = { ...localErrors, ...serverErrors }

  function handleChange(event) {
    const { name, value } = event.target
    setValues((prev) => ({ ...prev, [name]: value }))
  }

  /** Quick client-side checks; the API re-validates everything anyway. */
  function validate() {
    const found = {}
    if (!values.sku.trim()) found.sku = 'SKU is required.'
    if (!values.name.trim()) found.name = 'Name is required.'
    if (values.unit_price === '' || Number(values.unit_price) < 0) {
      found.unit_price = 'Enter a price of 0 or more.'
    }
    if (!isEdit && Number(values.quantity_in_stock) < 0) {
      found.quantity_in_stock = 'Quantity cannot be negative.'
    }
    if (Number(values.reorder_level) < 0) found.reorder_level = 'Reorder level cannot be negative.'
    return found
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const found = validate()
    setLocalErrors(found)
    if (Object.keys(found).length > 0) return

    // Build the JSON payload: numbers as numbers, empty selects as null.
    const payload = {
      sku: values.sku.trim(),
      name: values.name.trim(),
      description: values.description.trim() || null,
      category_id: values.category_id === '' ? null : Number(values.category_id),
      supplier_id: values.supplier_id === '' ? null : Number(values.supplier_id),
      unit_price: Number(values.unit_price),
      reorder_level: Number(values.reorder_level),
    }
    if (!isEdit) {
      // Quantity can only be set when creating; afterwards it changes through
      // stock movements so that every change is logged.
      payload.quantity_in_stock = Number(values.quantity_in_stock)
    }

    setSubmitting(true)
    try {
      await onSubmit(payload)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="card form" onSubmit={handleSubmit} noValidate aria-label="Product form">
      <h2>{isEdit ? `Edit product: ${product.sku}` : 'Add product'}</h2>

      <div className="form-grid">
        <div className="field">
          <label htmlFor="sku">SKU *</label>
          <input id="sku" name="sku" value={values.sku} onChange={handleChange} maxLength={50} />
          {errors.sku && <span className="error-text">{errors.sku}</span>}
        </div>

        <div className="field">
          <label htmlFor="name">Name *</label>
          <input id="name" name="name" value={values.name} onChange={handleChange} maxLength={100} />
          {errors.name && <span className="error-text">{errors.name}</span>}
        </div>

        <div className="field field-wide">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            name="description"
            rows={2}
            value={values.description}
            onChange={handleChange}
            maxLength={1000}
          />
          {errors.description && <span className="error-text">{errors.description}</span>}
        </div>

        <div className="field">
          <label htmlFor="category_id">Category</label>
          <select id="category_id" name="category_id" value={values.category_id} onChange={handleChange}>
            <option value="">— none —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {errors.category_id && <span className="error-text">{errors.category_id}</span>}
        </div>

        <div className="field">
          <label htmlFor="supplier_id">Supplier</label>
          <select id="supplier_id" name="supplier_id" value={values.supplier_id} onChange={handleChange}>
            <option value="">— none —</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {errors.supplier_id && <span className="error-text">{errors.supplier_id}</span>}
        </div>

        <div className="field">
          <label htmlFor="unit_price">Unit price *</label>
          <input
            id="unit_price"
            name="unit_price"
            type="number"
            min="0"
            step="0.01"
            value={values.unit_price}
            onChange={handleChange}
          />
          {errors.unit_price && <span className="error-text">{errors.unit_price}</span>}
        </div>

        <div className="field">
          <label htmlFor="quantity_in_stock">{isEdit ? 'In stock' : 'Initial quantity'}</label>
          <input
            id="quantity_in_stock"
            name="quantity_in_stock"
            type="number"
            min="0"
            step="1"
            value={values.quantity_in_stock}
            onChange={handleChange}
            disabled={isEdit}
          />
          {isEdit ? (
            <span className="hint">Quantity changes are recorded as stock movements.</span>
          ) : (
            errors.quantity_in_stock && <span className="error-text">{errors.quantity_in_stock}</span>
          )}
        </div>

        <div className="field">
          <label htmlFor="reorder_level">Reorder level</label>
          <input
            id="reorder_level"
            name="reorder_level"
            type="number"
            min="0"
            step="1"
            value={values.reorder_level}
            onChange={handleChange}
          />
          {errors.reorder_level && <span className="error-text">{errors.reorder_level}</span>}
        </div>
      </div>

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create product'}
        </button>
        <button type="button" className="btn" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export default ProductForm
