import { api } from '../api/client'
import LookupManager from '../components/LookupManager'
import { useApi } from '../hooks/useApi'

const CATEGORY_FIELDS = [{ name: 'name', label: 'Name', required: true }]

const SUPPLIER_FIELDS = [
  { name: 'name', label: 'Name', required: true },
  { name: 'email', label: 'E-mail', type: 'email', maxLength: 254 },
  { name: 'phone', label: 'Phone', type: 'tel', maxLength: 30 },
]

/** CRUD screens for the two lookup tables: categories and suppliers. */
function Manage() {
  const categories = useApi('/categories')
  const suppliers = useApi('/suppliers')

  return (
    <div className="page">
      <div className="page-header">
        <h1>Categories &amp; Suppliers</h1>
      </div>

      {(categories.error || suppliers.error) && (
        <p className="alert alert-error" role="alert">
          {categories.error || suppliers.error}
        </p>
      )}

      <div className="two-col">
        <LookupManager
          title="Categories"
          items={categories.data ? categories.data.items : []}
          fields={CATEGORY_FIELDS}
          onCreate={async (values) => {
            await api.post('/categories', values)
            categories.reload()
          }}
          onUpdate={async (id, values) => {
            await api.put(`/categories/${id}`, values)
            categories.reload()
          }}
          onDelete={async (item) => {
            await api.delete(`/categories/${item.id}`)
            categories.reload()
          }}
        />

        <LookupManager
          title="Suppliers"
          items={suppliers.data ? suppliers.data.items : []}
          fields={SUPPLIER_FIELDS}
          onCreate={async (values) => {
            await api.post('/suppliers', values)
            suppliers.reload()
          }}
          onUpdate={async (id, values) => {
            await api.put(`/suppliers/${id}`, values)
            suppliers.reload()
          }}
          onDelete={async (item) => {
            await api.delete(`/suppliers/${item.id}`)
            suppliers.reload()
          }}
        />
      </div>
    </div>
  )
}

export default Manage
