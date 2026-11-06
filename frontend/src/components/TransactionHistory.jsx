import { formatDateTime, formatNumber } from '../utils/format'

/**
 * Table of stock_transactions rows (newest first, as returned by the API).
 * `showProduct` adds SKU / product columns for the all-products view.
 */
function signedQuantity(tx) {
  if (tx.type === 'IN') return `+${formatNumber(tx.quantity)}`
  if (tx.type === 'OUT') return `−${formatNumber(tx.quantity)}`
  // ADJUSTMENT is stored signed already
  return tx.quantity > 0 ? `+${formatNumber(tx.quantity)}` : `−${formatNumber(Math.abs(tx.quantity))}`
}

function TransactionHistory({ transactions, showProduct = false, emptyMessage = 'No stock movements yet.' }) {
  if (!transactions || transactions.length === 0) {
    return <p className="empty-state">{emptyMessage}</p>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            {showProduct && <th>SKU</th>}
            {showProduct && <th>Product</th>}
            <th>Type</th>
            <th className="num">Quantity</th>
            <th>Reason</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((tx) => (
            <tr key={tx.id}>
              <td className="nowrap">{formatDateTime(tx.created_at)}</td>
              {showProduct && <td className="mono">{tx.sku}</td>}
              {showProduct && <td>{tx.product_name}</td>}
              <td>
                <span className={`tx-type tx-${tx.type.toLowerCase()}`}>{tx.type}</span>
              </td>
              <td className="num mono">{signedQuantity(tx)}</td>
              <td>{tx.reason || <span className="muted">—</span>}</td>
              <td className="cell-sub">{tx.note || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default TransactionHistory
