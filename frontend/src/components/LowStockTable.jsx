import { Link } from 'react-router-dom'
import { formatNumber } from '../utils/format'
import StockBadge from './StockBadge'

/** Alert table from GET /api/reports/low-stock (most urgent first). */
function LowStockTable({ items, limit }) {
  const rows = limit ? items.slice(0, limit) : items
  if (rows.length === 0) {
    return <p className="empty-state">No products are at or below their reorder level.</p>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product</th>
            <th>Supplier</th>
            <th className="num">Quantity</th>
            <th className="num">Reorder level</th>
            <th className="num">Shortfall</th>
            <th>Status</th>
            <th className="actions"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.id}>
              <td className="mono">{item.sku}</td>
              <td>{item.name}</td>
              <td>{item.supplier_name || <span className="muted">—</span>}</td>
              <td className="num">{formatNumber(item.quantity_in_stock)}</td>
              <td className="num">{formatNumber(item.reorder_level)}</td>
              <td className="num">{formatNumber(item.shortfall)}</td>
              <td>
                <StockBadge status={item.stock_status} />
              </td>
              <td className="actions">
                <Link to={`/stock?product=${item.id}`} className="btn btn-small">
                  Restock
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limit && items.length > limit && (
        <p className="table-footnote">
          Showing {limit} of {items.length} — <Link to="/reports">see all in Reports</Link>
        </p>
      )}
    </div>
  )
}

export default LowStockTable
