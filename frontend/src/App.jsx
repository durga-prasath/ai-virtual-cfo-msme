import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/auth/Login'
import Register from './pages/auth/Register'
import Dashboard from './pages/Dashboard'
import Customers from './pages/billing/Customers'
import Products from './pages/billing/Products'
import Invoices from './pages/billing/Invoices'
import CreateInvoice from './pages/billing/CreateInvoice'
import Payments from './pages/billing/Payments'
import GSTReports from './pages/gst/GSTReports'
import Purchases from './pages/purchases/Purchases'
import Forecasting from './pages/cfo/Forecasting'
import Alerts from './pages/cfo/Alerts'
import ERPSettings from './pages/erp/ERPSettings'
import Ledger from './pages/erp/Ledger'
import PLReport from './pages/erp/PLReport'
import Scanner from './pages/scanner/Scanner'
import Chatbot from './pages/chatbot/Chatbot'
import TallySync from './pages/erp/TallySync'

function PrivateRoute({ children }) {

  const { user, loading } = useAuth()
  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login"    element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected — wrapped in Layout (sidebar + navbar) */}
      <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"          element={<Dashboard />} />
        <Route path="chatbot"            element={<Chatbot />} />
        <Route path="scanner"            element={<Scanner />} />
        <Route path="billing/customers"  element={<Customers />} />
        <Route path="billing/products"   element={<Products />} />
        <Route path="billing/invoices"   element={<Invoices />} />
        <Route path="billing/invoices/new" element={<CreateInvoice />} />
        <Route path="billing/payments"   element={<Payments />} />
        <Route path="gst"                element={<GSTReports />} />
        <Route path="purchases"          element={<Purchases />} />
        <Route path="cfo/forecast"       element={<Forecasting />} />
        <Route path="cfo/alerts"         element={<Alerts />} />
        <Route path="erp/settings"       element={<ERPSettings />} />
        <Route path="erp/ledger"         element={<Ledger />} />
        <Route path="erp/pl"             element={<PLReport />} />
        <Route path="erp/tally"          element={<TallySync />} />
      </Route>


      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
