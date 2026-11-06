import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { bodyOfCall, mockFetch } from '../test/mockApi'
import StockMovements from './StockMovements'

const mouse = {
  id: 10, sku: 'ELEC-001', name: 'Wireless Mouse', quantity_in_stock: 12, reorder_level: 5, stock_status: 'in_stock',
}
const cable = {
  id: 11, sku: 'ELEC-002', name: 'USB-C Cable', quantity_in_stock: 0, reorder_level: 5, stock_status: 'out',
}
const history = {
  items: [
    { id: 3, product_id: 10, sku: 'ELEC-001', product_name: 'Wireless Mouse', type: 'OUT', quantity: 3, reason: 'Sale', note: null, created_at: '2026-11-05T10:00:00Z' },
    { id: 2, product_id: 10, sku: 'ELEC-001', product_name: 'Wireless Mouse', type: 'ADJUSTMENT', quantity: -2, reason: 'Stock count correction', note: 'Count', created_at: '2026-11-04T10:00:00Z' },
    { id: 1, product_id: 10, sku: 'ELEC-001', product_name: 'Wireless Mouse', type: 'IN', quantity: 17, reason: 'Initial stock', note: null, created_at: '2026-11-01T10:00:00Z' },
  ],
}

function renderPage(url = '/stock') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <StockMovements />
    </MemoryRouter>,
  )
}

function baseRoutes(extra = {}) {
  return {
    'GET /api/products': { items: [mouse, cable], total: 2 },
    'GET /api/stock/transactions': { items: history.items },
    'GET /api/products/10/transactions': history,
    ...extra,
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('StockMovements page', () => {
  it('deep-links to a product via ?product= and shows its history with signed quantities', async () => {
    mockFetch(baseRoutes())
    renderPage('/stock?product=10')
    const historyCard = (await screen.findByText(/^History/)).closest('section')
    expect(within(historyCard).getByText('+17')).toBeInTheDocument()
    expect(within(historyCard).getByText('−3')).toBeInTheDocument()
    expect(within(historyCard).getByText('−2')).toBeInTheDocument()
    expect(within(historyCard).getByText('ADJUSTMENT')).toBeInTheDocument()
    expect(screen.getByLabelText('Product *')).toHaveValue('10')
  })

  it('submits Stock Out with a numeric payload and shows the server confirmation', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(
      baseRoutes({
        'POST /api/stock/out': {
          status: 201,
          body: {
            transaction: { id: 9, sku: 'ELEC-001', type: 'OUT', quantity: 4 },
            product: { ...mouse, quantity_in_stock: 8 },
          },
        },
      }),
    )
    renderPage()
    await screen.findByText('Recent movements (all products)')
    await user.click(screen.getByRole('tab', { name: 'Stock Out' }))
    await user.selectOptions(screen.getByLabelText('Product *'), '10')
    await user.type(screen.getByLabelText('Quantity removed *'), '4')
    await user.type(screen.getByLabelText('Note'), 'INV-5')
    await user.click(screen.getByRole('button', { name: 'Remove stock' }))

    await waitFor(() => expect(bodyOfCall(fetchMock, 'POST', '/api/stock/out')).toBeDefined())
    expect(bodyOfCall(fetchMock, 'POST', '/api/stock/out')).toEqual({
      product_id: 10, quantity: 4, reason: 'Sale', note: 'INV-5',
    })
    expect(await screen.findByRole('status')).toHaveTextContent('ELEC-001: removed 4 — now 8 in stock.')
  })

  it('blocks an obvious over-withdrawal client-side (no request sent)', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(baseRoutes())
    renderPage()
    await screen.findByText('Recent movements (all products)')
    await user.click(screen.getByRole('tab', { name: 'Stock Out' }))
    await user.selectOptions(screen.getByLabelText('Product *'), '10')
    await user.type(screen.getByLabelText('Quantity removed *'), '500')
    await user.click(screen.getByRole('button', { name: 'Remove stock' }))
    expect(screen.getByText('Only 12 in stock.')).toBeInTheDocument()
    expect(bodyOfCall(fetchMock, 'POST', '/api/stock/out')).toBeUndefined()
  })

  it('shows the API error when the server rejects a withdrawal', async () => {
    const user = userEvent.setup()
    mockFetch(
      baseRoutes({
        'POST /api/stock/out': {
          status: 400,
          body: { error: 'Insufficient stock for ELEC-001: requested 12, only 2 available.', details: { quantity: 'Only 2 available.' } },
        },
      }),
    )
    renderPage()
    await screen.findByText('Recent movements (all products)')
    await user.click(screen.getByRole('tab', { name: 'Stock Out' }))
    await user.selectOptions(screen.getByLabelText('Product *'), '10')
    await user.type(screen.getByLabelText('Quantity removed *'), '12') // passes client check (12 <= 12)
    await user.click(screen.getByRole('button', { name: 'Remove stock' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient stock for ELEC-001')
    expect(screen.getByText('Only 2 available.')).toBeInTheDocument()
  })

  it('submits an adjustment as new_quantity', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch(
      baseRoutes({
        'POST /api/stock/adjust': {
          status: 201,
          body: {
            transaction: { id: 9, sku: 'ELEC-001', type: 'ADJUSTMENT', quantity: -2 },
            product: { ...mouse, quantity_in_stock: 10 },
          },
        },
      }),
    )
    renderPage('/stock?product=10')
    await screen.findByText('Recent movements (all products)')
    await user.click(screen.getByRole('tab', { name: 'Adjustment' }))
    await user.type(screen.getByLabelText('Counted quantity (new total) *'), '10')
    await user.click(screen.getByRole('button', { name: 'Apply adjustment' }))
    await waitFor(() => expect(bodyOfCall(fetchMock, 'POST', '/api/stock/adjust')).toBeDefined())
    expect(bodyOfCall(fetchMock, 'POST', '/api/stock/adjust')).toEqual({
      product_id: 10, new_quantity: 10, reason: 'Stock count correction', note: null,
    })
  })

  it('shows the out-of-stock badge for the selected product', async () => {
    const user = userEvent.setup()
    mockFetch(baseRoutes({ 'GET /api/products/11/transactions': { items: [] } }))
    renderPage()
    await screen.findByText('Recent movements (all products)')
    await user.selectOptions(screen.getByLabelText('Product *'), '11')
    expect((await screen.findAllByText('Out of stock')).length).toBeGreaterThan(0)
    expect(await screen.findByText('No stock movements yet.')).toBeInTheDocument()
  })
})
