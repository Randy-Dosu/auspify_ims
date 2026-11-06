import { render as rtlRender, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProductTable from './ProductTable'

// ProductTable contains a <Link>, so it must render inside a router.
const render = (ui) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>)

const product = {
  id: 1,
  sku: 'ELEC-001',
  name: 'Wireless Mouse',
  description: 'Optical',
  category_name: 'Electronics',
  supplier_name: 'Accra Tech',
  unit_price: 85,
  quantity_in_stock: 12,
  reorder_level: 5,
  stock_status: 'in_stock',
}

describe('ProductTable', () => {
  it('shows an empty-state message when there are no products', () => {
    render(<ProductTable products={[]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('No products found.')).toBeInTheDocument()
  })

  it('renders product fields', () => {
    render(<ProductTable products={[product]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('ELEC-001')).toBeInTheDocument()
    expect(screen.getByText('Wireless Mouse')).toBeInTheDocument()
    expect(screen.getByText('Electronics')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('In stock')).toBeInTheDocument()
  })

  it('shows the right badge for each stock status', () => {
    render(
      <ProductTable
        products={[
          { ...product, id: 1, stock_status: 'in_stock' },
          { ...product, id: 2, sku: 'B', stock_status: 'low' },
          { ...product, id: 3, sku: 'C', stock_status: 'out' },
        ]}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('In stock')).toHaveClass('badge-in_stock')
    expect(screen.getByText('Low stock')).toHaveClass('badge-low')
    expect(screen.getByText('Out of stock')).toHaveClass('badge-out')
  })

  it('links each row to its stock history', () => {
    render(<ProductTable products={[product]} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'History' })).toHaveAttribute('href', '/stock?product=1')
  })

  it('escapes HTML in product data (stored XSS is rendered as text)', () => {
    const evil = { ...product, name: '<img src=x onerror="alert(1)">', description: '<b>bold</b>' }
    const { container } = render(
      <ProductTable products={[evil]} onEdit={vi.fn()} onDelete={vi.fn()} />,
    )
    // The literal text is visible...
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument()
    expect(screen.getByText('<b>bold</b>')).toBeInTheDocument()
    // ...but no element was actually created from it.
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
  })

  it('calls onEdit / onDelete with the product', () => {
    const onEdit = vi.fn()
    const onDelete = vi.fn()
    render(<ProductTable products={[product]} onEdit={onEdit} onDelete={onDelete} />)
    screen.getByRole('button', { name: 'Edit' }).click()
    screen.getByRole('button', { name: 'Delete' }).click()
    expect(onEdit).toHaveBeenCalledWith(product)
    expect(onDelete).toHaveBeenCalledWith(product)
  })
})
