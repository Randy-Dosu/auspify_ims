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

/** Shape of GET /api/products with pagination metadata. */
function listResponse(items, extra = {}) {
  return { items, total: items.length, page: 1, per_page: 20, total_pages: 1, sort: 'name', order: 'asc', ...extra }
}

/** The query string of the most recent GET /api/products call. */
function lastListQuery(fetchMock) {
  const calls = fetchMock.mock.calls.filter(([url, o]) => (o?.method || 'GET') === 'GET' && url.startsWith('/api/products?'))
  return calls.length ? new URLSearchParams(calls[calls.length - 1][0].split('?')[1]) : null
}

function renderPage(url = '/products') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Products />
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Products page', () => {
  it('loads and lists products from the API', async () => {
    mockFetch({
      'GET /api/products': listResponse([mouse]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    expect(await screen.findByText('Wireless Mouse')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('1 product')
  })

  it('creates a product: sends a typed JSON payload and refreshes the table', async () => {
    const user = userEvent.setup()
    let products = [mouse]
    const created = { ...mouse, id: 11, sku: 'NEW-001', name: 'New Thing', unit_price: 9.5, quantity_in_stock: 3 }
    const fetchMock = mockFetch({
      'GET /api/products': () => listResponse(products),
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
    const form = within(screen.getByRole('form', { name: 'Product form' }))
    await user.type(form.getByLabelText('SKU *'), 'NEW-001')
    await user.type(form.getByLabelText('Name *'), 'New Thing')
    await user.selectOptions(form.getByLabelText('Category'), '1')
    await user.selectOptions(form.getByLabelText('Supplier'), '2')
    await user.type(form.getByLabelText('Unit price *'), '9.5')
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
      'GET /api/products': listResponse([mouse]),
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
      'GET /api/products': listResponse([]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('No products yet.')
    await user.click(screen.getByRole('button', { name: '+ Add product' }))
    await user.click(screen.getByRole('button', { name: 'Create product' }))
    expect(screen.getByText('SKU is required.')).toBeInTheDocument()
    expect(screen.getByText('Name is required.')).toBeInTheDocument()
    expect(bodyOfCall(fetchMock, 'POST', '/api/products')).toBeUndefined()
  })

  it('edits a product: quantity is locked and PUT omits it', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([mouse]),
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
      'GET /api/products': () => listResponse(products),
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
    expect(await screen.findByText('No products yet.')).toBeInTheDocument()
  })
})

describe('Products page - search, filters, sorting, pagination', () => {
  const cable = { ...mouse, id: 11, sku: 'ELEC-002', name: 'USB-C Cable', quantity_in_stock: 0, stock_status: 'out' }

  it('sends default list parameters and shows the results count', async () => {
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([mouse, cable]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    expect(lastListQuery(fetchMock).toString()).toBe('sort=name&order=asc&page=1&per_page=20')
    expect(screen.getByRole('status')).toHaveTextContent('2 products')
  })

  it('debounces the search box and queries ?search=', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([mouse]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    const callsBefore = fetchMock.mock.calls.length
    await user.type(screen.getByLabelText('Search'), 'mou')
    // Nothing fired per keystroke...
    expect(fetchMock.mock.calls.length).toBe(callsBefore)
    // ...but one request after the pause.
    await waitFor(() => expect(lastListQuery(fetchMock).get('search')).toBe('mou'))
    expect(lastListQuery(fetchMock).get('page')).toBe('1')
  })

  it('applies dropdown filters immediately and reflects a deep-linked status filter', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([cable]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage('/products?stock_status=out')
    await screen.findByText('USB-C Cable')
    expect(lastListQuery(fetchMock).get('stock_status')).toBe('out')
    expect(screen.getByLabelText('Stock level')).toHaveValue('out')
    expect(screen.getByRole('status')).toHaveTextContent('1 product match your filters')

    await user.selectOptions(screen.getByLabelText('Category'), '1')
    await waitFor(() => expect(lastListQuery(fetchMock).get('category')).toBe('1'))
    expect(lastListQuery(fetchMock).get('stock_status')).toBe('out') // combined
  })

  it('shows an empty-results message and Clear filters resets everything', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': () => listResponse([]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage('/products?search=zzz&category=1&min_price=5')
    expect(await screen.findByText('No products match these filters. Try clearing some of them.')).toBeInTheDocument()
    expect(screen.getByLabelText('Search')).toHaveValue('zzz')
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(lastListQuery(fetchMock).toString()).toBe('sort=name&order=asc&page=1&per_page=20'))
    expect(screen.getByLabelText('Search')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeDisabled()
  })

  it('clicking a column header sorts ascending, then descending', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([mouse]),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    await user.click(screen.getByRole('columnheader', { name: /Unit price/ }))
    await waitFor(() => expect(lastListQuery(fetchMock).get('sort')).toBe('unit_price'))
    expect(lastListQuery(fetchMock).get('order')).toBe('asc')
    expect(screen.getByRole('columnheader', { name: /Unit price/ })).toHaveAttribute('aria-sort', 'ascending')
    await user.click(screen.getByRole('columnheader', { name: /Unit price/ }))
    await waitFor(() => expect(lastListQuery(fetchMock).get('order')).toBe('desc'))
    expect(screen.getByRole('columnheader', { name: /Unit price/ })).toHaveAttribute('aria-sort', 'descending')
  })

  it('paginates: shows counts, Next requests page 2, Previous disabled on page 1', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch({
      'GET /api/products': listResponse([mouse], { total: 45, total_pages: 3, per_page: 20 }),
      'GET /api/categories': categories,
      'GET /api/suppliers': suppliers,
    })
    renderPage()
    await screen.findByText('Wireless Mouse')
    expect(screen.getByText('Showing 1–20 of 45')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '‹ Previous' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Next ›' }))
    await waitFor(() => expect(lastListQuery(fetchMock).get('page')).toBe('2'))
    await user.selectOptions(screen.getByLabelText(/Per page/), '50')
    await waitFor(() => expect(lastListQuery(fetchMock).get('per_page')).toBe('50'))
    expect(lastListQuery(fetchMock).get('page')).toBe('1') // per-page change resets to page 1
  })
})
