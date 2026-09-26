import { useEffect, useState } from 'react'
import { createUserRequest, deactivateUserRequest, listUsersRequest } from '../services/authApi'
import './Users.css'

const ROLES = ['admin', 'reviewer', 'operator', 'viewer']

export default function Users() {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    role: 'viewer',
  })

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listUsersRequest()
      setItems(data.items || [])
    } catch (err) {
      setError(err.message || 'Failed to load users.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onCreate = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')
    try {
      await createUserRequest(form)
      setSuccess(`Created user “${form.username}”.`)
      setForm({ username: '', email: '', password: '', role: 'viewer' })
      await load()
    } catch (err) {
      setError(err.message || 'Failed to create user.')
    }
  }

  const onDeactivate = async (user) => {
    setError('')
    setSuccess('')
    try {
      await deactivateUserRequest(user.id)
      setSuccess(`Deactivated “${user.username}”.`)
      await load()
    } catch (err) {
      setError(err.message || 'Failed to deactivate user.')
    }
  }

  return (
    <div className="users-page">
      <header className="users-page__header">
        <div>
          <h2>Users</h2>
          <p>Admin-only local account management. Passwords are stored hashed.</p>
        </div>
      </header>

      {error && <div className="users-page__banner users-page__banner--error">{error}</div>}
      {success && <div className="users-page__banner users-page__banner--ok">{success}</div>}

      <form className="users-page__form" onSubmit={onCreate}>
        <h3>Create user</h3>
        <label>
          Username
          <input
            value={form.username}
            onChange={(e) => setForm((prev) => ({ ...prev, username: e.target.value }))}
            required
            minLength={3}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={form.password}
            onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
            required
            minLength={8}
          />
        </label>
        <label>
          Role
          <select
            value={form.role}
            onChange={(e) => setForm((prev) => ({ ...prev, role: e.target.value }))}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Create</button>
      </form>

      <section className="users-page__list">
        <h3>Existing users</h3>
        {loading ? (
          <p>Loading…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((user) => (
                <tr key={user.id}>
                  <td>{user.username}</td>
                  <td>{user.email}</td>
                  <td>{user.role}</td>
                  <td>{user.is_active ? 'Yes' : 'No'}</td>
                  <td>
                    {user.is_active && (
                      <button type="button" onClick={() => onDeactivate(user)}>
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
