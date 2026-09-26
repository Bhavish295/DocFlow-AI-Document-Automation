import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { navigationItems } from '../../data/navigation'
import './Sidebar.css'

function Sidebar({ open, onClose }) {
  const { isAdmin } = useAuth()
  const items = navigationItems.filter(
    (item) =>
      (item.path !== '/users' && item.path !== '/audit-logs') || isAdmin,
  )

  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`} aria-label="Primary">
      <div className="sidebar__brand">
        <div className="sidebar__mark" aria-hidden="true">
          <span />
          <span />
        </div>
        <div className="sidebar__brand-text">
          <p className="sidebar__product">DocFlow</p>
          <p className="sidebar__tagline">Document Automation</p>
        </div>
        <button
          type="button"
          className="sidebar__close"
          onClick={onClose}
          aria-label="Close navigation"
        >
          ×
        </button>
      </div>

      <nav className="sidebar__nav">
        <p className="sidebar__section-label">Workspace</p>
        <ul className="sidebar__list">
          {items.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `sidebar__link ${isActive ? 'is-active' : ''}`
                }
              >
                <span className="sidebar__link-indicator" aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar__footer">
        <p className="sidebar__env">Local platform</p>
        <p className="sidebar__hint">Documents · validation · AI assistants</p>
      </div>
    </aside>
  )
}

export default Sidebar
