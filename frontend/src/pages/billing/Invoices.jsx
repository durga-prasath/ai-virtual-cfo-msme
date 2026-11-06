import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { billingAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

const STATUS_BADGE = {
  draft:     'badge-gray',
  sent:      'badge-blue',
  paid:      'badge-green',
  overdue:   'badge-red',
  cancelled: 'badge-gray',
}

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

export default function Invoices() {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading]   = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const navigate = useNavigate()

  useEffect(() => { fetchInvoices() }, [statusFilter])

  async function fetchInvoices() {
    setLoading(true)
    try {
      const params = statusFilter ? { status: statusFilter } : {}
      const res = await billingAPI.getInvoices(params)
      setInvoices(res.data?.invoices || res.data || [])
    } catch { toast.error('Failed to load invoices') }
    finally { setLoading(false) }
  }

  async function handleSend(id, e) {
    e.stopPropagation()
    try {
      await billingAPI.sendInvoice(id)
      toast.success('Invoice sent')
      fetchInvoices()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Sales Invoices</h1>
        <button className="btn-primary" onClick={() => navigate('/billing/invoices/new')}>
          <PlusIcon className="w-4 h-4" /> New Invoice
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {['', 'draft', 'sent', 'paid', 'overdue'].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={clsx('px-3 py-1.5 text-sm rounded-lg border transition-colors',
              statusFilter === s
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
            )}
          >
            {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="table-th">Invoice #</th>
                <th className="table-th">Date</th>
                <th className="table-th">Due Date</th>
                <th className="table-th text-right">Total</th>
                <th className="table-th text-right">Due</th>
                <th className="table-th">Status</th>
                <th className="table-th"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="text-center py-10 text-gray-400">Loading…</td></tr>
              ) : invoices.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-10 text-gray-400">No invoices found</td></tr>
              ) : invoices.map(inv => (
                <tr key={inv.id} className="table-row cursor-pointer" onClick={() => {}}>
                  <td className="table-td font-mono font-semibold text-blue-700">{inv.invoice_number}</td>
                  <td className="table-td text-gray-500">{inv.invoice_date?.slice(0,10)}</td>
                  <td className="table-td text-gray-500">{inv.due_date?.slice(0,10)}</td>
                  <td className="table-td text-right font-medium">{fmt(inv.total_amount)}</td>
                  <td className="table-td text-right">{fmt(inv.amount_due)}</td>
                  <td className="table-td">
                    <span className={STATUS_BADGE[inv.status] || 'badge-gray'}>
                      {inv.status}
                    </span>
                  </td>
                  <td className="table-td">
                    {inv.status === 'draft' && (
                      <button
                        onClick={(e) => handleSend(inv.id, e)}
                        className="text-xs text-blue-600 hover:underline"
                      >
                        Send
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
