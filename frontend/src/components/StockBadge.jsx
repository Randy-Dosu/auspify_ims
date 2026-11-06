/**
 * Visual stock-level indicator. The status itself is computed by the API
 * (product.stock_status) so the rule lives in exactly one place:
 *   out      -> quantity == 0
 *   low      -> 0 < quantity <= reorder_level
 *   in_stock -> quantity > reorder_level
 */
const LABELS = {
  out: 'Out of stock',
  low: 'Low stock',
  in_stock: 'In stock',
}

function StockBadge({ status }) {
  const label = LABELS[status] || status
  return <span className={`badge badge-${status}`}>{label}</span>
}

export default StockBadge
