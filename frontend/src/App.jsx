import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import Dashboard from './pages/Dashboard'
import Manage from './pages/Manage'
import Products from './pages/Products'
import Reports from './pages/Reports'
import StockMovements from './pages/StockMovements'
import './App.css'

/** Root component: navigation bar + one route per page. */
function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <main className="container">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/stock" element={<StockMovements />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/manage" element={<Manage />} />
          <Route path="*" element={<p className="empty-state">Page not found.</p>} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
