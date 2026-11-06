import { useEffect, useState } from 'react'
import { paymentsAPI, billingAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon } from '@heroicons/react/24/outline'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

export default function Payments() {
  const [payments, setPayments] = useState([])
  const [invoices, setInvoices] = useState([])
  const [customers, setCustomers] = useState([])
  const [loading, setLoading]   = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    sales_invoice_id: '', customer_id: '',
    amount: '', payment_method: 'bank_transfer',
    direction: 'incoming', payment_date: new Date().toISOString().slice(0, 10),
    transaction_reference: '',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      paymentsAPI.getPayments(),
      billingAPI.getInvoices({ status: 'sent' }),
      billingAPI.getCustomers(),
    ]).then(([p, i, c]) => {
      setPayments(p.data?.payments || p.data || [])
      setInvoices(i.data?.invoices || i.data || [])
      setCustomers(c.data?.customers || c.data || [])
    }).catch(() => toast.error('Failed to load')).finally(() => setLoading(false))
  }, [])

  async function handleRecord(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = {
        ...form,
        amount: String(form.amount),
        payment_date: new Date(form.payment_date).toISOString(),
      }
      await paymentsAPI.recordPayment(payload)
      toast.success('Payment recorded')
      setShowForm(false)
      const p = await paymentsAPI.getPayments()
      setPayments(p.data?.payments || p.data || [])
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to record payment')
    } finally { setSaving(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Payments</h1>
        <button className="btn-primary" onClick={() => setShowForm(p => !p)}>
          <PlusIcon className="w-4 h-4" /> Record Payment
        </button>
      </div>

      {showForm && (
        <div className="card p-6">
          <h2 className="font-semibold mb-4">Record Payment</h2>
          <form onSubmit={handleRecord} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Invoice (Sent)</label>
              <select className="input" value={form.sales_invoice_id}
                onChange={e => {
                  const inv = invoices.find(i => i.id === e.target.value)
                  setForm(p => ({ ...p, sales_invoice_id: e.target.value,
                    customer_id: inv?.customer_id || p.customer_id,
                    amount: inv?.amount_due || p.amount }))
                }}>
                <option value="">Select invoice…</option>
                {invoices.map(i => <option key={i.id} value={i.id}>{i.invoice_number} — {fmt(i.amount_due)}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Customer *</label>
              <select required className="input" value={form.customer_id}
                onChange={e => setForm(p => ({ ...p, customer_id: e.target.value }))}>
                <option value="">Select customer…</option>
                {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Amount (Rs.) *</label>
              <input required type="number" step="0.01" className="input" value={form.amount}
                onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} />
            </div>
            <div>
              <label className="label">Payment Method</label>
              <select className="input" value={form.payment_method}
                onChange={e => setForm(p => ({ ...p, payment_method: e.target.value }))}>
                <option value="bank_transfer">Bank Transfer</option>
                <option value="upi">UPI</option>
                <option value="cheque">Cheque</option>
                <option value="cash">Cash</option>
                <option value="card">Card</option>
              </select>
            </div>
            <div>
              <label className="label">Payment Date *</label>
              <input required type="date" className="input" value={form.payment_date}
                onChange={e => setForm(p => ({ ...p, payment_date: e.target.value }))} />
            </div>
            <div>
              <label className="label">Reference / UTR</label>
              <input className="input" placeholder="UTR/Txn ID" value={form.transaction_reference}
                onChange={e => setForm(p => ({ ...p, transaction_reference: e.target.value }))} />
            </div>
            <div className="flex items-end gap-2 sm:col-span-2">
              <button type="submit" disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Record'}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="table-th">Date</th>
                <th className="table-th">Invoice</th>
                <th className="table-th text-right">Amount</th>
                <th className="table-th">Method</th>
                <th className="table-th">Reference</th>
                <th className="table-th">Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="text-center py-10 text-gray-400">Loading…</td></tr>
              ) : payments.length === 0 ? (
                <tr><td colSpan={6} className="text-center py-10 text-gray-400">No payments yet</td></tr>
              ) : payments.map(p => (
                <tr key={p.id} className="table-row">
                  <td className="table-td text-gray-500">{p.payment_date?.slice(0,10)}</td>
                  <td className="table-td font-mono text-xs text-blue-700">{p.invoice_number || '—'}</td>
                  <td className="table-td text-right font-semibold">{fmt(p.amount)}</td>
                  <td className="table-td text-gray-500">{p.payment_method?.replace(/_/g, ' ')}</td>
                  <td className="table-td font-mono text-xs">{p.transaction_reference || '—'}</td>
                  <td className="table-td"><span className="badge-green">{p.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
