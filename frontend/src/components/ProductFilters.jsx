import DebouncedInput from './DebouncedInput'

const STATUS_OPTIONS = [
  { value: '', label: 'Any stock level' },
  { value: 'in_stock', label: 'In stock' },
  { value: 'low', label: 'Low stock' },
  { value: 'out', label: 'Out of stock' },
]

/**
 * Search + filter bar for the Products page.
 *
 * Props
 *   filters     current values: {search, category, supplier, stock_status, min_price, max_price}
 *   categories  [{id, name}]
 *   suppliers   [{id, name}]
 *   onChange(partial)   merge new values into the filters (page resets to 1)
 *   onClear()
 */
function ProductFilters({ filters, categories, suppliers, onChange, onClear }) {
  const active = Object.values(filters).some((v) => v !== '')

  return (
    <form className="filters card" onSubmit={(e) => e.preventDefault()} aria-label="Product filters">
      <div className="field filter-search">
        <label htmlFor="filter-search">Search</label>
        <DebouncedInput
          id="filter-search"
          type="search"
          placeholder="Name or SKU…"
          maxLength={100}
          value={filters.search}
          onCommit={(search) => onChange({ search })}
        />
      </div>

      <div className="field">
        <label htmlFor="filter-category">Category</label>
        <select id="filter-category" value={filters.category} onChange={(e) => onChange({ category: e.target.value })}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="filter-supplier">Supplier</label>
        <select id="filter-supplier" value={filters.supplier} onChange={(e) => onChange({ supplier: e.target.value })}>
          <option value="">All suppliers</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="filter-status">Stock level</label>
        <select
          id="filter-status"
          value={filters.stock_status}
          onChange={(e) => onChange({ stock_status: e.target.value })}
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="field filter-price">
        <label htmlFor="filter-min-price">Price from</label>
        <DebouncedInput
          id="filter-min-price"
          type="number"
          min="0"
          step="0.01"
          placeholder="0"
          value={filters.min_price}
          onCommit={(min_price) => onChange({ min_price })}
        />
      </div>

      <div className="field filter-price">
        <label htmlFor="filter-max-price">Price to</label>
        <DebouncedInput
          id="filter-max-price"
          type="number"
          min="0"
          step="0.01"
          placeholder="∞"
          value={filters.max_price}
          onCommit={(max_price) => onChange({ max_price })}
        />
      </div>

      <div className="field filter-actions">
        <button type="button" className="btn" onClick={onClear} disabled={!active}>
          Clear filters
        </button>
      </div>
    </form>
  )
}

export default ProductFilters
