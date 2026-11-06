import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'

/**
 * Dashboard. For now it shows simple counts from the list endpoints;
 * richer summary cards arrive with the reports module (Step 3).
 */
function Dashboard() {
  const products = useApi('/products')
  const categories = useApi('/categories')
  const suppliers = useApi('/suppliers')

  const count = (resource, key = 'items') =>
    resource.loading ? '…' : resource.data ? resource.data[key].length : '!'

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <div className="stat-grid">
        <Link to="/products" className="stat-card">
          <span className="stat-label">Products</span>
          <span className="stat-value">{count(products)}</span>
        </Link>
        <Link to="/manage" className="stat-card">
          <span className="stat-label">Categories</span>
          <span className="stat-value">{count(categories)}</span>
        </Link>
        <Link to="/manage" className="stat-card">
          <span className="stat-label">Suppliers</span>
          <span className="stat-value">{count(suppliers)}</span>
        </Link>
      </div>

      {(products.error || categories.error || suppliers.error) && (
        <p className="alert alert-error" role="alert">
          {products.error || categories.error || suppliers.error}
        </p>
      )}
    </div>
  )
}

export default Dashboard
