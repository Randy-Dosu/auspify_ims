import { Link } from 'react-router-dom'
import { formatMoney, formatNumber } from '../utils/format'

/**
 * The five headline numbers from GET /api/reports/summary.
 * Each card links to the page where the user can act on the number.
 */
function SummaryCards({ summary }) {
  const cards = [
    { label: 'Products', value: formatNumber(summary.total_products), to: '/products' },
    { label: 'Units in stock', value: formatNumber(summary.total_units), to: '/products' },
    { label: 'Inventory value', value: formatMoney(summary.total_value), to: '/reports' },
    {
      label: 'Low stock',
      value: formatNumber(summary.low_stock_count),
      to: '/products?stock_status=low',
      tone: summary.low_stock_count > 0 ? 'warn' : '',
    },
    {
      label: 'Out of stock',
      value: formatNumber(summary.out_of_stock_count),
      to: '/products?stock_status=out',
      tone: summary.out_of_stock_count > 0 ? 'danger' : '',
    },
  ]
  return (
    <div className="stat-grid">
      {cards.map((card) => (
        <Link key={card.label} to={card.to} className={`stat-card ${card.tone ? `stat-${card.tone}` : ''}`}>
          <span className="stat-label">{card.label}</span>
          <span className="stat-value">{card.value}</span>
        </Link>
      ))}
    </div>
  )
}

export default SummaryCards
