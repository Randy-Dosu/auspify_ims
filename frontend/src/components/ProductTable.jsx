import { formatMoney, formatNumber } from '../utils/format'

/**
 * Read-only table of products with Edit / Delete actions.
 *
 * React escapes every value it renders ({product.name} etc.), so a product
 * named "<img src=x onerror=...>" is displayed as literal text, never run.
 */
function ProductTable({ products, onEdit, onDelete }) {
  if (!products || products.length === 0) {
    return <p className="empty-state">No products found.</p>
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>Name</th>
            <th>Category</th>
            <th>Supplier</th>
            <th className="num">Unit price</th>
            <th className="num">In stock</th>
            <th className="num">Reorder level</th>
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
              <td className="num">{formatNumber(product.reorder_level)}</td>
              <td className="actions">
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
