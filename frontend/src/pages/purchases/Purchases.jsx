import { useEffect, useState } from 'react'
import { purchasesAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

export default function Purchases() {
  const [tab, setTab]           = useState('invoices')
  const [invoices, setInvoices] = useState([])
  const [vendors, setVendors]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [showVendorForm, setShowVendorForm] = useState(false)
  const [vendorForm, setVendorForm] = useState({ name: '', gstin: '', email: '', phone: '', state: '' })
  const [uploading, setUploading] = useState(false)
  const [ocrResult, setOcrResult] = useState(null)

  useEffect(() => {
    Promise.all([
      purchasesAPI.getInvoices(),
      purchasesAPI.getVendors(),
    ]).then(([i, v]) => {
      setInvoices(i.data?.invoices || i.data || [])
      setVendors(v.data?.vendors   || v.data || [])
    }).catch(() => toast.error('Failed to load purchases'))
    .finally(() => setLoading(false))
  }, [])

  async function handleCreateVendor(e) {
    e.preventDefault()
    try {
      const payload = Object.fromEntries(
        Object.entries(vendorForm).map(([k, v]) => [k, typeof v === 'string' && !v.trim() ? null : v.trim()])
      )
      await purchasesAPI.createVendor(payload)
      toast.success('Vendor added')
      setShowVendorForm(false)
      const v = await purchasesAPI.getVendors()
      setVendors(v.data?.vendors || v.data || [])
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }


  async function handleOCRUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setOcrResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await purchasesAPI.uploadOCR(fd)
      setOcrResult(res.data)
      toast.success('OCR extraction complete')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'OCR failed')
    } finally { setUploading(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Purchases</h1>
        <div className="flex gap-2">
          <label className={clsx('btn-secondary cursor-pointer', uploading && 'opacity-50')}>
            <ArrowUpTrayIcon className="w-4 h-4" />
            {uploading ? 'Processing…' : 'Upload Bill (OCR)'}
            <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden"
              onChange={handleOCRUpload} disabled={uploading} />
          </label>
          <button className="btn-primary" onClick={() => setShowVendorForm(p => !p)}>
            <PlusIcon className="w-4 h-4" /> Add Vendor
          </button>
        </div>
      </div>

      {/* OCR Result */}
      {ocrResult && (
        <div className="card p-5 border-blue-200 bg-blue-50">
          <h3 className="font-semibold text-blue-800 mb-3">OCR Extraction Result</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {[
              { label: 'Vendor', val: ocrResult.vendor_name },
              { label: 'Invoice #', val: ocrResult.invoice_number },
              { label: 'Date', val: ocrResult.invoice_date },
              { label: 'Total', val: fmt(ocrResult.total_amount) },
              { label: 'CGST', val: fmt(ocrResult.cgst) },
              { label: 'SGST', val: fmt(ocrResult.sgst) },
              { label: 'IGST', val: fmt(ocrResult.igst) },
              { label: 'Confidence', val: ocrResult.confidence ? `${(ocrResult.confidence*100).toFixed(0)}%` : '—' },
            ].map(f => (
              <div key={f.label}>
                <p className="text-xs text-blue-500 font-medium">{f.label}</p>
                <p className="font-semibold text-blue-900">{f.val || '—'}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Vendor form */}
      {showVendorForm && (
        <div className="card p-6">
          <h2 className="font-semibold mb-4">New Vendor</h2>
          <form onSubmit={handleCreateVendor} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><label className="label">Name *</label>
              <input required className="input" value={vendorForm.name}
                onChange={e => setVendorForm(p => ({ ...p, name: e.target.value }))} /></div>
            <div><label className="label">GSTIN</label>
              <input className="input" value={vendorForm.gstin}
                onChange={e => setVendorForm(p => ({ ...p, gstin: e.target.value }))} /></div>
            <div><label className="label">Email</label>
              <input type="email" className="input" value={vendorForm.email}
                onChange={e => setVendorForm(p => ({ ...p, email: e.target.value }))} /></div>
            <div><label className="label">State</label>
              <input className="input" value={vendorForm.state}
                onChange={e => setVendorForm(p => ({ ...p, state: e.target.value }))} /></div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary">Save</button>
              <button type="button" className="btn-secondary" onClick={() => setShowVendorForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2">
        {['invoices', 'vendors'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={clsx('px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              tab === t ? 'bg-blue-600 text-white' : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50')}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Invoices table */}
      {tab === 'invoices' && (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="table-th">Invoice #</th>
                  <th className="table-th">Date</th>
                  <th className="table-th text-right">Total</th>
                  <th className="table-th text-right">Due</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">OCR</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="text-center py-10 text-gray-400">Loading…</td></tr>
                ) : invoices.length === 0 ? (
                  <tr><td colSpan={6} className="text-center py-10 text-gray-400">No purchase invoices yet</td></tr>
                ) : invoices.map(inv => (
                  <tr key={inv.id} className="table-row">
                    <td className="table-td font-mono text-xs">{inv.invoice_number}</td>
                    <td className="table-td text-gray-500">{inv.invoice_date?.slice(0,10)}</td>
                    <td className="table-td text-right font-medium">{fmt(inv.total_amount)}</td>
                    <td className="table-td text-right">{fmt(inv.amount_due)}</td>
                    <td className="table-td"><span className="badge-blue">{inv.status}</span></td>
                    <td className="table-td">{inv.ocr_extracted ? <span className="badge-green">OCR</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Vendors table */}
      {tab === 'vendors' && (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="table-th">Vendor Name</th>
                  <th className="table-th">GSTIN</th>
                  <th className="table-th">Email</th>
                  <th className="table-th">State</th>
                </tr>
              </thead>
              <tbody>
                {vendors.length === 0 ? (
                  <tr><td colSpan={4} className="text-center py-10 text-gray-400">No vendors yet</td></tr>
                ) : vendors.map(v => (
                  <tr key={v.id} className="table-row">
                    <td className="table-td font-medium">{v.name}</td>
                    <td className="table-td font-mono text-xs">{v.gstin || '—'}</td>
                    <td className="table-td text-gray-500">{v.email || '—'}</td>
                    <td className="table-td">{v.state || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
