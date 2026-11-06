// This page is rolled into GSTReports.jsx and billing/Invoices.jsx
// Redirect to GST reports
import { Navigate } from 'react-router-dom'
export default function SalesReports() {
  return <Navigate to="/gst" replace />
}
