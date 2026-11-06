import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { bodyOfCall, mockFetch } from '../test/mockApi'
import Products from './Products'

const categories = { items: [{ id: 1, name: 'Electronics', product_count: 1 }] }
const suppliers = { items: [{ id: 2, name: 'Accra Tech', product_count: 1 }] }
const mouse = {
  id: 10,
  sku: 'ELEC-001',
  name: 'Wireless Mouse',
  description: null,
  category_id: 1,
  category_name: 'Electronics',
  supplier_id: 2,
  supplier_name: 'Accra Tech',
  unit_price: 85,
  quantity_in_stock: 12,
  reorder_level: 5,
  created_at: '2026-11-01T10:00:00Z',
  updated_at: '2026-11-01T10:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Products />
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Products page', () => {
  it('loads and lists products from the API', async () => {
    mockFetch({
      'GET /api/products': { items: [mouse], total: 1 },
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    expect(await screen.findByText('Wireless Mouse')).toBeInTheDocument()
    expect(screen.getByText('1 products')).toBeInTheDocument()
  })

  it('creates a product: sends a typed JSON payload and refreshes the table', async () => {
    const user = userEvent.setup()
    let products = [mouse]
    const created = { ...mouse, id: 11, sku: 'NEW-001', name: 'New Thing', unit_price: 9.5, quantity_in_stock: 3 }
    const fetchMock = mockFetch({
      'GET /api/products': () => ({ items: products, total: products.length }),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
      'POST /api/products': () => {
        products = [...products, created]
        return { status: 201, body: created }
      },
    })
    renderPage()
    await screen.findByText('Wireless Mouse')

    await user.click(screen.getByRole('button', { name: '+ Add product' }))
    await user.type(screen.getByLabelText('SKU *'), 'NEW-001')
    await user.type(screen.getByLabelText('Name *'), 'New Thing')
    await user.selectOptions(screen.getByLabelText('Category'), '1')
    await user.selectOptions(screen.getByLabelText('Supplier'), '2')
    await user.type(screen.getByLabelText('Unit price *'), '9.5')
    await user.clear(screen.getByLabelText('Initial quantity'))
    await user.type(screen.getByLabelText('Initial quantity'), '3')
    await user.click(screen.getByRole('button', { name: 'Create product' }))

    // The payload must contain real numbers, not strings from the inputs.
    await waitFor(() => expect(bodyOfCall(fetchMock, 'POST', '/api/products')).toBeDefined())
    expect(bodyOfCall(fetchMock, 'POST', '/api/products')).toEqual({
      sku: 'NEW-001',
      name: 'New Thing',
      description: null,
      category_id: 1,
      supplier_id: 2,
      unit_price: 9.5,
      reorder_level: 10,
      quantity_in_stock: 3,
    })
    expect(await screen.findByText('New Thing')).toBeInTheDocument()
    expect(screen.getByText('Product "New Thing" created.')).toBeInTheDocument()
  })

  it('shows server validation errors under the right field (duplicate SKU)', async () => {
    const user = userEvent.setup()
    mockFetch({
      'GET /api/products': { items: [mouse], total: 1 },
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
      'POST /api/products': {
        status: 409,
        body: { error: 'A product with this SKU already exists.', details: { sku: 'Already exists.' } },
      },
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    await user.click(screen.getByRole('button', { name: '+ Add product' }))
    await user.type(screen.getByLabelText('SKU *'), 'ELEC-001')
    await user.type(screen.getByLabelText('Name *'), 'Dup')
    await user.type(screen.getByLabelText('Unit price *'), '1')
    await user.click(screen.getByRole('button', { name: 'Create product' }))

    expect(await screen.findByText('A product with this SKU already exists.')).toBeInTheDocument()
    expect(screen.getByText('Already exists.')).toBeInTheDocument()
    // Form stays open so the user can fix the value.
    expect(screen.getByLabelText('SKU *')).toHaveValue('ELEC-001')
  })

  it('blocks submission client-side when required fields are empty', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': { items: [], total: 0 },
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('No products found.')
    await user.click(screen.getByRole('button', { name: '+ Add product' }))
    await user.click(screen.getByRole('button', { name: 'Create product' }))
    expect(screen.getByText('SKU is required.')).toBeInTheDocument()
    expect(screen.getByText('Name is required.')).toBeInTheDocument()
    expect(bodyOfCall(fetchMock, 'POST', '/api/products')).toBeUndefined()
  })

  it('edits a product: quantity is locked and PUT omits it', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': { items: [mouse], total: 1 },
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
      'PUT /api/products/10': { ...mouse, name: 'Renamed Mouse' },
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText('In stock')).toBeDisabled()
    const nameInput = screen.getByLabelText('Name *')
    await user.clear(nameInput)
    await user.type(nameInput, 'Renamed Mouse')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(bodyOfCall(fetchMock, 'PUT', '/api/products/10')).toBeDefined())
    const body = bodyOfCall(fetchMock, 'PUT', '/api/products/10')
    expect(body.name).toBe('Renamed Mouse')
    expect(body).not.toHaveProperty('quantity_in_stock')
  })

  it('deletes a product after confirmation', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let products = [mouse]
    const fetchMock = mockFetch({
      'GET /api/products': () => ({ items: products, total: products.length }),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
      'DELETE /api/products/10': () => {
        products = []
        return { status: 204, body: null }
      },
    })
    renderPage()
    const row = (await screen.findByText('Wireless Mouse')).closest('tr')
    await user.click(within(row).getByRole('button', { name: 'Delete' }))
    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/products/10', expect.objectContaining({ method: 'DELETE' })),
    )
    expect(await screen.findByText('No products found.')).toBeInTheDocument()
  })
})
