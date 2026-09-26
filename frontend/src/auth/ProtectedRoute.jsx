import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

export default function ProtectedRoute({ children, permission }) {
  const { isAuthenticated, loading, can } = useAuth()
  const location = useLocation()

  if (loading) {
    return <div className="auth-loading">Loading session…</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (permission && !can(permission)) {
    return (
      <div className="auth-denied">
        <h2>Access denied</h2>
        <p>Your role does not have permission to view this page.</p>
      </div>
    )
  }

  return children
}
