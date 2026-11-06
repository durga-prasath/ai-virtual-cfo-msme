import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})
// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auto-logout on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ─── Auth ────────────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post('/auth/register', data),
  login:    (data) => api.post('/auth/login', data),
  me:       ()     => api.get('/auth/me'),
}

// ─── Billing ─────────────────────────────────────────────────
export const billingAPI = {
  // Customers
  getCustomers:    (params) => api.get('/billing/customers', { params }),
  createCustomer:  (data)   => api.post('/billing/customers', data),
  getCustomer:     (id)     => api.get(`/billing/customers/${id}`),
  // Products
  getProducts:     (params) => api.get('/billing/products', { params }),
  createProduct:   (data)   => api.post('/billing/products', data),
  // Invoices
  getInvoices:     (params) => api.get('/billing/invoices', { params }),
  createInvoice:   (data)   => api.post('/billing/invoices', data),
  getInvoice:      (id)     => api.get(`/billing/invoices/${id}`),
  sendInvoice:     (id)     => api.patch(`/invoices/${id}/send`),
  cancelInvoice:   (id)     => api.patch(`/invoices/${id}/cancel`),
}

// ─── Payments ────────────────────────────────────────────────
export const paymentsAPI = {
  recordPayment: (data)   => api.post('/payments', data),
  getPayments:   (params) => api.get('/payments', { params }),
}

// ─── GST ─────────────────────────────────────────────────────
export const gstAPI = {
  gstr1:          (params) => api.get('/gst/gstr1', { params }),
  gstr3b:         (params) => api.get('/gst/gstr3b', { params }),
  liability:      (params) => api.get('/gst/liability', { params }),
  reconciliation: (params) => api.get('/gst/reconciliation', { params }),
  records:        (params) => api.get('/gst/records', { params }),
  fileReturn:     (data)   => api.post('/gst/file', data),
}

// ─── Purchases / OCR ─────────────────────────────────────────
export const purchasesAPI = {
  getVendors:       (params) => api.get('/purchases/vendors', { params }),
  createVendor:     (data)   => api.post('/purchases/vendors', data),
  getInvoices:      (params) => api.get('/purchases/invoices', { params }),
  createInvoice:    (data)   => api.post('/purchases/invoices', data),
  uploadOCR:        (formData) =>
    api.post('/purchases/invoices/ocr-upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// ─── Forecasting / Dashboard ─────────────────────────────────
export const cfoAPI = {
  generateForecast: (data)   => api.post('/cfo/forecast', data),
  listForecasts:    (params) => api.get('/cfo/forecasts', { params }),
  getDashboard:     ()       => api.get('/cfo/dashboard'),
}

// ─── Alerts ──────────────────────────────────────────────────
export const alertsAPI = {
  list:        (params) => api.get('/alerts', { params }),
  summary:     ()       => api.get('/alerts/summary'),
  markRead:    (data)   => api.post('/alerts/mark-read', data),
  markAllRead: ()       => api.post('/alerts/mark-all-read'),
  dismiss:     (id)     => api.post(`/alerts/${id}/dismiss`),
  scan:        ()       => api.post('/alerts/scan'),
}

// ─── ERP ─────────────────────────────────────────────────────
export const erpAPI = {
  getBusiness:    ()       => api.get('/erp/business'),
  updateBusiness: (data)   => api.patch('/erp/business', data),
  getConfig:      ()       => api.get('/erp/config'),
  sync:           (data)   => api.post('/erp/sync', data),
  getLedger:      (params) => api.get('/erp/ledger', { params }),
  createLedger:   (data)   => api.post('/erp/ledger', data),
  getPL:          (params) => api.get('/erp/reports/pl', { params }),
  getTrialBalance:(params) => api.get('/erp/reports/trial', { params }),
  // Phase 9 Tally XML
  getTallySummary:   () => api.get('/erp/tally/summary'),
  exportInvoicesXml: () => api.get('/erp/tally/export/invoices', { responseType: 'blob' }),
  exportPurchasesXml:() => api.get('/erp/tally/export/purchases', { responseType: 'blob' }),
  exportPaymentsXml: () => api.get('/erp/tally/export/payments', { responseType: 'blob' }),
}

// ─── Phase 6: Document Scanner ────────────────────────────────
export const ocrAPI = {
  getSupportedTypes: () => api.get('/ocr/supported-types'),
  scan: (formData) =>
    api.post('/ocr/scan', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  confirm: (data) => api.post('/ocr/confirm', data),
}

// ─── Phase 7: AI CFO Chatbot ──────────────────────────────────
export const chatbotAPI = {
  ask: (data) => api.post('/chatbot/ask', data),
  getSuggested: () => api.get('/chatbot/suggested'),
}

