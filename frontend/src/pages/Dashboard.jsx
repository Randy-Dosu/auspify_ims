import { Link } from 'react-router-dom'
import LowStockTable from '../components/LowStockTable'
import SummaryCards from '../components/SummaryCards'
import { useApi } from '../hooks/useApi'
import { formatNumber } from '../utils/format'

/**
 * Dashboard: headline numbers, items that need reordering and the products
 * that moved the most in the last 30 days (the API's default range).
 */
function Dashboard() {
  const summary = useApi('/reports/summary')
  const lowStock = useApi('/reports/low-stock')
  const topMoving = useApi('/reports/top-moving-products?limit=5')

  const error = summary.error || lowStock.error || topMoving.error

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <div className="header-actions">
          <Link to="/stock" className="btn">
            Record movement
          </Link>
          <Link to="/products" className="btn btn-primary">
            + Add product
          </Link>
        </div>
      </div>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}

      {summary.loading && !summary.data && <p className="muted">Loading summary…</p>}
      {summary.data && <SummaryCards summary={summary.data} />}

      <div className="two-col">
        <section className="card">
          <h2>Needs reordering</h2>
          {lowStock.data && <LowStockTable items={lowStock.data.items} limit={5} />}
        </section>

        <section className="card">
          <h2>Top moving products (last 30 days)</h2>
          {topMoving.data && topMoving.data.items.length === 0 && (
            <p className="empty-state">No stock has gone out in this period.</p>
          )}
          {topMoving.data && topMoving.data.items.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Product</th>
                    <th className="num">Units out</th>
                    <th className="num">Units in</th>
                    <th className="num">In stock</th>
                  </tr>
                </thead>
                <tbody>
                  {topMoving.data.items.map((item) => (
                    <tr key={item.id}>
                      <td className="mono">{item.sku}</td>
                      <td>{item.name}</td>
                      <td className="num">{formatNumber(item.units_out)}</td>
                      <td className="num">{formatNumber(item.units_in)}</td>
                      <td className="num">{formatNumber(item.quantity_in_stock)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

export default Dashboard
