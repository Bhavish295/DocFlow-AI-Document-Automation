import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import ProtectedRoute from './auth/ProtectedRoute'
import { Permission } from './auth/permissions'
import AIAssistant from './pages/AIAssistant'
import Analytics from './pages/Analytics'
import AuditLogs from './pages/AuditLogs'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'
import IngestionHistory from './pages/IngestionHistory'
import Invoices from './pages/Invoices'
import Login from './pages/Login'
import PurchaseOrders from './pages/PurchaseOrders'
import ReviewQueue from './pages/ReviewQueue'
import Users from './pages/Users'
import Validation from './pages/Validation'
import Vendors from './pages/Vendors'
import Workflows from './pages/Workflows'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/ingestion" element={<IngestionHistory />} />
        <Route path="/invoices" element={<Invoices />} />
        <Route path="/vendors" element={<Vendors />} />
        <Route path="/purchase-orders" element={<PurchaseOrders />} />
        <Route path="/validation" element={<Validation />} />
        <Route path="/review-queue" element={<ReviewQueue />} />
        <Route path="/ai-assistant" element={<AIAssistant />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route
          path="/users"
          element={
            <ProtectedRoute permission={Permission.USERS_MANAGE}>
              <Users />
            </ProtectedRoute>
          }
        />
        <Route
          path="/audit-logs"
          element={
            <ProtectedRoute permission={Permission.USERS_MANAGE}>
              <AuditLogs />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default App
