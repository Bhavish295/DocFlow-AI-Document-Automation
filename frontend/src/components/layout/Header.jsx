import { useAuth } from '../../auth/AuthContext'
import './Header.css'

function Header({ title, onMenuClick }) {
  const { user, logout } = useAuth()

  return (
    <header className="app-header">
      <div className="app-header__left">
        <button
          type="button"
          className="app-header__menu"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <span />
          <span />
          <span />
        </button>
        <div>
          <p className="app-header__eyebrow">Operations console</p>
          <h1 className="app-header__title">{title}</h1>
        </div>
      </div>
      <div className="app-header__right">
        <div className="app-header__status">
          <span className="app-header__pulse" aria-hidden="true" />
          System ready
        </div>
        {user && (
          <div className="app-header__user">
            <div>
              <strong>{user.username}</strong>
              <span>{user.role}</span>
            </div>
            <button type="button" className="app-header__logout" onClick={logout}>
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

export default Header
