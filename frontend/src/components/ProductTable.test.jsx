import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProductTable from './ProductTable'

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
