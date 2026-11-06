import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockFetch } from '../test/mockApi'
import Dashboard from './Dashboard'
import Reports from './Reports'

const summary = {
  total_products: 22, total_units: 834, total_value: 96129, low_stock_count: 3, out_of_stock_count: 2,
  total_categories: 6, total_suppliers: 4, total_transactions: 161,
}
const lowStock = {
  total: 2,
  items: [
    { id: 3, sku: 'ELEC-003', name: 'Bluetooth Keyboard', supplier_name: 'Accra Tech', quantity_in_stock: 0, reorder_level: 10, shortfall: 10, stock_status: 'out' },
    { id: 8, sku: 'OFF-003', name: 'Stapler', supplier_name: null, quantity_in_stock: 4, reorder_level: 8, shortfall: 4, stock_status: 'low' },
  ],
}
const valuation = {
  total_value: 54912,
  items: [
    { category_id: 3, category_name: 'Furniture', product_count: 3, total_units: 27, total_value: 29990 },
    { category_id: 1, category_name: 'Electronics', product_count: 5, total_units: 169, total_value: 24922 },
  ],
}
const movements = {
  from: '2026-10-08', to: '2026-11-06',
  days: [{ day: '2026-11-05', stock_in: 10, stock_out: 4, adjustments: 0, transactions: 2, net: 6 }],
  totals: { stock_in: 396, stock_out: 655, adjustments: 3, transactions: 100 },
}
const topMoving = {
  from: '2026-10-08', to: '2026-11-06',
  items: [{ id: 16, sku: 'BEV-001', name: 'Bottled Water', category_name: 'Beverages', units_out: 66, units_in: 92, transactions: 8, quantity_in_stock: 40 }],
}

const EMPTY_SUMMARY = Object.fromEntries(Object.keys(summary).map((k) => [k, 0]))

function routes(overrides = {}) {
  return {
    'GET /api/reports/summary': summary,
    'GET /api/reports/low-stock': lowStock,
    'GET /api/reports/valuation-by-category': valuation,
    'GET /api/reports/movements': movements,
    'GET /api/reports/top-moving-products': topMoving,
    ...overrides,
  }
}

const wrap = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)

afterEach(() => vi.unstubAllGlobals())

describe('Dashboard', () => {
  it('renders summary cards, low-stock alerts and top movers from the API', async () => {
    mockFetch(routes())
    wrap(<Dashboard />)
    expect(await screen.findByText('22')).toBeInTheDocument() // products
    expect(screen.getByText('834')).toBeInTheDocument() // units
    expect(screen.getByText('Low stock', { selector: '.stat-label' }).closest('a')).toHaveClass('stat-warn')
    expect(screen.getByText('Out of stock', { selector: '.stat-label' }).closest('a')).toHaveClass('stat-danger')
    expect(await screen.findByText('Bluetooth Keyboard')).toBeInTheDocument()
    expect(screen.getByText('Bottled Water')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Restock' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Restock' })[0]).toHaveAttribute('href', '/stock?product=3')
  })

  it('shows zeros and friendly empty states for an empty database (no errors)', async () => {
    mockFetch(
      routes({
        'GET /api/reports/summary': EMPTY_SUMMARY,
        'GET /api/reports/low-stock': { items: [], total: 0 },
        'GET /api/reports/top-moving-products': { items: [] },
      }),
    )
    wrap(<Dashboard />)
    expect(await screen.findByText('No products are at or below their reorder level.')).toBeInTheDocument()
    expect(screen.getByText('No stock has gone out in this period.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(4)
  })
})

describe('Reports', () => {
  it('renders charts, category table with total, top movers and low-stock table', async () => {
    mockFetch(routes())
    wrap(<Reports />)
    expect(await screen.findByTestId('movements-chart')).toBeInTheDocument()
    expect(await screen.findByTestId('valuation-chart')).toBeInTheDocument()
    expect(screen.getByText('Furniture')).toBeInTheDocument()
    expect(screen.getByText('Electronics')).toBeInTheDocument()
    expect(screen.getByText('396')).toBeInTheDocument() // units in total
    expect(screen.getByText('BEV-001')).toBeInTheDocument()
    expect(screen.getByText('ELEC-003')).toBeInTheDocument()
    const totalRow = screen.getByText('Total').closest('tr')
    expect(within(totalRow).getByText('8')).toBeInTheDocument() // 3 + 5 products
  })

  it('exposes CSV export links that point at the API', async () => {
    mockFetch(routes())
    wrap(<Reports />)
    await screen.findByTestId('movements-chart')
    const links = screen.getAllByRole('link', { name: 'Export CSV' })
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/api/reports/valuation-by-category?format=csv',
      '/api/reports/low-stock?format=csv',
    ])
    links.forEach((a) => expect(a).toHaveAttribute('download'))
  })

  it('re-queries movements and top movers with the chosen date range', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(routes())
    wrap(<Reports />)
    await screen.findByTestId('movements-chart')

    const form = screen.getByRole('form', { name: 'Date range' })
    const [fromInput, toInput] = within(form).getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/)
    // Set the inputs directly (date inputs do not accept typed text in jsdom).
    await user.clear(fromInput)
    await user.type(fromInput, '2026-10-01')
    await user.clear(toInput)
    await user.type(toInput, '2026-10-07')
    await user.click(within(form).getByRole('button', { name: 'Apply' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/reports/movements?from=2026-10-01&to=2026-10-07', expect.anything()),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/reports/top-moving-products?from=2026-10-01&to=2026-10-07&limit=10',
      expect.anything(),
    )
  })

  it('shows the API error for an invalid range instead of crashing', async () => {
    mockFetch(
      routes({
        'GET /api/reports/movements': { status: 400, body: { error: 'Validation failed.', details: { from: "'from' must not be after 'to'." } } },
      }),
    )
    wrap(<Reports />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Validation failed.')
    expect(await screen.findByTestId('valuation-chart')).toBeInTheDocument() // rest of the page still renders
  })
})
