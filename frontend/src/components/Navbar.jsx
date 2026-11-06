import { NavLink } from 'react-router-dom'

/** Top navigation. NavLink adds the "active" class to the current page. */
const LINKS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/products', label: 'Products' },
  { to: '/stock', label: 'Stock Movements' },
  { to: '/reports', label: 'Reports' },
  { to: '/manage', label: 'Categories & Suppliers' },
]

function Navbar() {
  return (
    <header className="navbar">
      <div className="navbar-inner">
        <NavLink to="/" className="brand">
          Auspify <span>IMS</span>
        </NavLink>
        <nav aria-label="Main navigation">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

export default Navbar
