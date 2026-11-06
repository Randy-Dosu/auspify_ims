import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import LowStockTable from '../components/LowStockTable'
import SummaryCards from '../components/SummaryCards'
import { useApi } from '../hooks/useApi'
import { formatMoney, formatNumber } from '../utils/format'

/** YYYY-MM-DD for a date `daysAgo` days before today (local time). */
function isoDaysAgo(daysAgo) {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

const PRESETS = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
]

/**
 * Reports dashboard:
 *   - summary cards
 *   - stock movements over time (line chart, filterable by date range)
 *   - inventory value by category (bar chart)
 *   - top moving products for the range
 *   - low-stock alert table with CSV export
 */
function Reports() {
  const [from, setFrom] = useState(() => isoDaysAgo(29))
  const [to, setTo] = useState(() => isoDaysAgo(0))
  // The applied range only changes when the user clicks "Apply" (or a preset),
  // so typing in the date inputs does not fire a request per keystroke.
  const [range, setRange] = useState({ from: isoDaysAgo(29), to: isoDaysAgo(0) })

  const summary = useApi('/reports/summary')
  const valuation = useApi('/reports/valuation-by-category')
  const lowStock = useApi('/reports/low-stock')
  const movements = useApi(`/reports/movements?from=${range.from}&to=${range.to}`)
  const topMoving = useApi(`/reports/top-moving-products?from=${range.from}&to=${range.to}&limit=10`)

  function applyRange(event) {
    event.preventDefault()
    setRange({ from, to })
  }

  function applyPreset(days) {
    const next = { from: isoDaysAgo(days - 1), to: isoDaysAgo(0) }
    setFrom(next.from)
    setTo(next.to)
    setRange(next)
  }

  const movementDays = movements.data ? movements.data.days : []
  const valuationItems = valuation.data ? valuation.data.items : []

  return (
    <div className="page">
      <div className="page-header">
        <h1>Reports</h1>
      </div>

      {summary.data && <SummaryCards summary={summary.data} />}

      {/* ---- Stock movements over time ---- */}
      <section className="card">
        <div className="card-header">
          <h2>Stock movements over time</h2>
          <form className="range-form" onSubmit={applyRange} aria-label="Date range">
            <label>
              From{' '}
              <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label>
              To{' '}
              <input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
            </label>
            <button type="submit" className="btn btn-small">
              Apply
            </button>
            {PRESETS.map((preset) => (
              <button
                key={preset.days}
                type="button"
                className="btn btn-small"
                onClick={() => applyPreset(preset.days)}
              >
                {preset.label}
              </button>
            ))}
          </form>
        </div>

        {movements.error && (
          <p className="alert alert-error" role="alert">
            {movements.error}
          </p>
        )}
        {movements.data && (
          <>
            <p className="muted">
              {movements.data.from} → {movements.data.to}: <strong>{formatNumber(movements.data.totals.stock_in)}</strong>{' '}
              units in, <strong>{formatNumber(movements.data.totals.stock_out)}</strong> units out,{' '}
              {formatNumber(movements.data.totals.transactions)} transactions
            </p>
            <div className="chart" data-testid="movements-chart">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={movementDays} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="day" tick={{ fontSize: 12 }} minTickGap={24} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="stock_in" name="Stock in" stroke="#16a34a" dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="stock_out" name="Stock out" stroke="#dc2626" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </section>

      <div className="two-col">
        {/* ---- Value by category ---- */}
        <section className="card">
          <div className="card-header">
            <h2>Inventory value by category</h2>
            <a className="btn btn-small" href="/api/reports/valuation-by-category?format=csv" download>
              Export CSV
            </a>
          </div>
          {valuation.data && valuationItems.length === 0 && <p className="empty-state">No products yet.</p>}
          {valuationItems.length > 0 && (
            <>
              <div className="chart" data-testid="valuation-chart">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={valuationItems} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="category_name" tick={{ fontSize: 11 }} interval={0} />
                    <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => formatNumber(v)} />
                    <Tooltip formatter={(value) => formatMoney(value)} />
                    <Bar dataKey="total_value" name="Value" fill="#2563eb" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="num">Products</th>
                      <th className="num">Units</th>
                      <th className="num">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {valuationItems.map((item) => (
                      <tr key={item.category_id ?? 'none'}>
                        <td>{item.category_name}</td>
                        <td className="num">{formatNumber(item.product_count)}</td>
                        <td className="num">{formatNumber(item.total_units)}</td>
                        <td className="num">{formatMoney(item.total_value)}</td>
                      </tr>
                    ))}
                    <tr className="row-total">
                      <td>Total</td>
                      <td className="num">{formatNumber(valuationItems.reduce((s, i) => s + i.product_count, 0))}</td>
                      <td className="num">{formatNumber(valuationItems.reduce((s, i) => s + i.total_units, 0))}</td>
                      <td className="num">{formatMoney(valuation.data.total_value)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        {/* ---- Top moving products ---- */}
        <section className="card">
          <h2>Top moving products ({range.from} → {range.to})</h2>
          {topMoving.data && topMoving.data.items.length === 0 && (
            <p className="empty-state">No stock went out in this period.</p>
          )}
          {topMoving.data && topMoving.data.items.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>SKU</th>
                    <th>Product</th>
                    <th>Category</th>
                    <th className="num">Units out</th>
                    <th className="num">Units in</th>
                    <th className="num">Transactions</th>
                  </tr>
                </thead>
                <tbody>
                  {topMoving.data.items.map((item) => (
                    <tr key={item.id}>
                      <td className="mono">{item.sku}</td>
                      <td>{item.name}</td>
                      <td>{item.category_name || <span className="muted">—</span>}</td>
                      <td className="num">{formatNumber(item.units_out)}</td>
                      <td className="num">{formatNumber(item.units_in)}</td>
                      <td className="num">{formatNumber(item.transactions)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* ---- Low stock alerts ---- */}
      <section className="card">
        <div className="card-header">
          <h2>Low-stock alerts {lowStock.data && <span className="muted">({lowStock.data.total})</span>}</h2>
          <a className="btn btn-small" href="/api/reports/low-stock?format=csv" download>
            Export CSV
          </a>
        </div>
        {lowStock.data && <LowStockTable items={lowStock.data.items} />}
      </section>
    </div>
  )
}

export default Reports
