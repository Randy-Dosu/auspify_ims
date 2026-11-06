import { Link } from 'react-router-dom'
import { formatMoney, formatNumber } from '../utils/format'
import StockBadge from './StockBadge'

/**
 * Table of products with Edit / Delete / History actions.
 *
 * Sorting: when `sort`, `order` and `onSort` are given, the column headers
 * become clickable. Clicking the active column flips the direction.
 *
 * React escapes every value it renders ({product.name} etc.), so a product
 * named "<img src=x onerror=...>" is displayed as literal text, never run.
 */
const COLUMNS = [
  { key: 'sku', label: 'SKU' },
  { key: 'name', label: 'Name' },
  { key: 'category', label: 'Category' },
  { key: 'supplier', label: 'Supplier' },
  { key: 'unit_price', label: 'Unit price', className: 'num' },
  { key: 'quantity_in_stock', label: 'Quantity', className: 'num' },
  { key: null, label: 'Status' },
  { key: 'reorder_level', label: 'Reorder level', className: 'num' },
]

function ProductTable({ products, onEdit, onDelete, sort, order, onSort, emptyMessage = 'No products found.' }) {
  if (!products || products.length === 0) {
    return <p className="empty-state">{emptyMessage}</p>
  }

  function header(column) {
    const sortable = Boolean(onSort && column.key)
    const active = sortable && sort === column.key
    const ariaSort = active ? (order === 'desc' ? 'descending' : 'ascending') : undefined
    return (
      <th
        key={column.label}
        className={`${column.className || ''} ${sortable ? 'sortable' : ''}`.trim()}
        aria-sort={ariaSort}
        onClick={sortable ? () => onSort(column.key) : undefined}
      >
        {column.label}
        {active && <span className="sort-indicator">{order === 'desc' ? '▼' : '▲'}</span>}
      </th>
    )
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {COLUMNS.map(header)}
            <th className="actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <tr key={product.id}>
              <td className="mono">{product.sku}</td>
              <td>
                <div className="cell-title">{product.name}</div>
                {product.description && <div className="cell-sub">{product.description}</div>}
              </td>
              <td>{product.category_name || <span className="muted">—</span>}</td>
              <td>{product.supplier_name || <span className="muted">—</span>}</td>
              <td className="num">{formatMoney(product.unit_price)}</td>
              <td className="num">{formatNumber(product.quantity_in_stock)}</td>
              <td>
                <StockBadge status={product.stock_status} />
              </td>
              <td className="num">{formatNumber(product.reorder_level)}</td>
              <td className="actions">
                <Link to={`/stock?product=${product.id}`} className="btn btn-small">
                  History
                </Link>
                <button type="button" className="btn btn-small" onClick={() => onEdit(product)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-small btn-danger"
                  onClick={() => onDelete(product)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ProductTable
