import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import LookupManager from './LookupManager'

const fields = [
  { name: 'name', label: 'Name', required: true },
  { name: 'email', label: 'E-mail' },
]
const items = [
  { id: 1, name: 'Accra Tech', email: 'a@b.co', product_count: 3 },
  { id: 2, name: 'Unused Co', email: null, product_count: 0 },
]

function setup(overrides = {}) {
  const props = {
    title: 'Suppliers',
    items,
    fields,
    onCreate: vi.fn().mockResolvedValue(),
    onUpdate: vi.fn().mockResolvedValue(),
    onDelete: vi.fn().mockResolvedValue(),
    ...overrides,
  }
  render(<LookupManager {...props} />)
  return props
}

describe('LookupManager', () => {
  it('lists items with product counts', () => {
    setup()
    expect(screen.getByText('Accra Tech')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('creates an item, sending blank optional fields as null', async () => {
    const user = userEvent.setup()
    const props = setup()
    await user.type(screen.getByLabelText('Name *'), '  New Supplier ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(props.onCreate).toHaveBeenCalledWith({ name: 'New Supplier', email: null }))
    // Form resets after a successful create.
    expect(screen.getByLabelText('Name *')).toHaveValue('')
  })

  it('edits an existing item', async () => {
    const user = userEvent.setup()
    const props = setup()
    const row = screen.getByText('Accra Tech').closest('tr')
    await user.click(within(row).getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText('Name *')).toHaveValue('Accra Tech')
    await user.clear(screen.getByLabelText('E-mail'))
    await user.type(screen.getByLabelText('E-mail'), 'new@b.co')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(props.onUpdate).toHaveBeenCalledWith(1, { name: 'Accra Tech', email: 'new@b.co' }))
  })

  it('disables Delete for items still in use and confirms before deleting', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const props = setup()
    const usedRow = screen.getByText('Accra Tech').closest('tr')
    expect(within(usedRow).getByRole('button', { name: 'Delete' })).toBeDisabled()

    const freeRow = screen.getByText('Unused Co').closest('tr')
    await user.click(within(freeRow).getByRole('button', { name: 'Delete' }))
    expect(window.confirm).toHaveBeenCalledWith('Delete "Unused Co"?')
    await waitFor(() => expect(props.onDelete).toHaveBeenCalledWith(items[1]))
  })

  it('shows the API error message when a request fails', async () => {
    const user = userEvent.setup()
    const error = Object.assign(new Error('A category with this name already exists.'), {
      details: { name: 'Already exists.' },
    })
    setup({ onCreate: vi.fn().mockRejectedValue(error) })
    await user.type(screen.getByLabelText('Name *'), 'Dup')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A category with this name already exists.')
    expect(screen.getByText('Already exists.')).toBeInTheDocument()
  })
})
