import { useEffect, useState } from 'react'
import { erpAPI } from '../../services/api'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

const ENTRY_BADGE = {
  invoice_raised:      'badge-blue',
  payment_received:    'badge-green',
  credit_note:         'badge-yellow',
  debit_note:          'badge-yellow',
  bad_debt_write_off:  'badge-red',
  revenue_adjustment:  'badge-purple',
}

export default function Ledger() {
  const [entries, setEntries]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [filters, setFilters]     = useState({ from_date: '', to_date: '', entry_type: '', unsynced_only: false })
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm] = useState({
    entry_type: 'revenue_adjustment', description: '', gross_amount: '',
    cgst_amount: '0', sgst_amount: '0', igst_amount: '0', discount_amount: '0',
    entry_date: new Date().toISOString().slice(0, 16),
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => { fetchLedger() }, [filters])

  async function fetchLedger() {
    setLoading(true)
    try {
      const params = {}
      if (filters.from_date)    params.from_date     = filters.from_date
      if (filters.to_date)      params.to_date       = filters.to_date
      if (filters.entry_type)   params.entry_type    = filters.entry_type
      if (filters.unsynced_only) params.unsynced_only = true
      const res = await erpAPI.getLedger(params)
      setEntries(res.data || [])
    } catch { toast.error('Failed to load ledger') }
    finally { setLoading(false) }
  }

  async function handleCreate(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await erpAPI.createLedger({
        ...form,
        gross_amount: form.gross_amount,
        cgst_amount:  form.cgst_amount,
        sgst_amount:  form.sgst_amount,
        igst_amount:  form.igst_amount,
        discount_amount: form.discount_amount,
        entry_date:   new Date(form.entry_date).toISOString(),
      })
      toast.success('Ledger entry created')
      setShowForm(false)
      fetchLedger()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setSaving(false) }
  }

  const setF = (k) => (e) => setFilters(p => ({...p, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value}))

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-gray-900">Revenue Ledger</h1>
        <button className="btn-primary" onClick={() => setShowForm(p => !p)}>+ Manual Entry</button>
      </div>

      {/* Manual entry form */}
      {showForm && (
        <div className="card p-6">
          <h2 className="font-semibold mb-4">New Ledger Entry</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Entry Type</label>
              <select className="input" value={form.entry_type}
                onChange={e => setForm(p => ({...p, entry_type: e.target.value}))}>
                <option value="revenue_adjustment">Revenue Adjustment</option>
                <option value="bad_debt_write_off">Bad Debt Write-Off</option>
                <option value="credit_note">Credit Note</option>
                <option value="debit_note">Debit Note</option>
              </select>
            </div>
            <div>
              <label className="label">Entry Date</label>
              <input type="datetime-local" className="input" value={form.entry_date}
                onChange={e => setForm(p => ({...p, entry_date: e.target.value}))} />
            </div>
            <div className="sm:col-span-2">
              <label className="label">Description *</label>
              <input required className="input" value={form.description}
                onChange={e => setForm(p => ({...p, description: e.target.value}))} />
            </div>
            {[
              { label: 'Gross Amount *', key: 'gross_amount', required: true },
              { label: 'Discount',       key: 'discount_amount' },
              { label: 'CGST',           key: 'cgst_amount' },
              { label: 'SGST',           key: 'sgst_amount' },
              { label: 'IGST',           key: 'igst_amount' },
            ].map(f => (
              <div key={f.key}>
                <label className="label">{f.label}</label>
                <input required={f.required} type="number" step="0.01" className="input"
                  value={form[f.key]} onChange={e => setForm(p => ({...p, [f.key]: e.target.value}))} />
              </div>
            ))}
            <div className="flex gap-2 sm:col-span-2">
              <button type="submit" disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Create Entry'}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="card p-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="label">From</label>
          <input type="date" className="input w-36" value={filters.from_date} onChange={setF('from_date')} />
        </div>
        <div>
          <label className="label">To</label>
          <input type="date" className="input w-36" value={filters.to_date} onChange={setF('to_date')} />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input w-48" value={filters.entry_type} onChange={setF('entry_type')}>
            <option value="">All types</option>
            <option value="invoice_raised">Invoice Raised</option>
            <option value="payment_received">Payment Received</option>
            <option value="credit_note">Credit Note</option>
            <option value="debit_note">Debit Note</option>
            <option value="bad_debt_write_off">Bad Debt Write-Off</option>
            <option value="revenue_adjustment">Revenue Adjustment</option>
          </select>
        </div>
        <div className="flex items-center gap-2 pb-0.5">
          <input type="checkbox" id="unsynced" className="w-4 h-4"
            checked={filters.unsynced_only} onChange={setF('unsynced_only')} />
          <label htmlFor="unsynced" className="text-sm text-gray-700">Unsynced only</label>
        </div>
      </div>

      {/* Table */}
      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="table-th">Date</th>
                <th className="table-th">Type</th>
                <th className="table-th">Description</th>
                <th className="table-th text-right">Gross</th>
                <th className="table-th text-right">Tax</th>
                <th className="table-th text-right">Net</th>
                <th className="table-th">FY / Qtr</th>
                <th className="table-th">Synced</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="text-center py-10 text-gray-400">Loading…</td></tr>
              ) : entries.length === 0 ? (
                <tr><td colSpan={8} className="text-center py-10 text-gray-400">No entries found</td></tr>
              ) : entries.map(e => (
                <tr key={e.id} className="table-row">
                  <td className="table-td text-gray-500 whitespace-nowrap">{e.entry_date?.slice(0,10)}</td>
                  <td className="table-td">
                    <span className={ENTRY_BADGE[e.entry_type] || 'badge-gray'}>
                      {e.entry_type?.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="table-td max-w-xs truncate" title={e.description}>{e.description}</td>
                  <td className="table-td text-right">{fmt(e.gross_amount)}</td>
                  <td className="table-td text-right text-gray-500">{fmt(e.total_tax)}</td>
                  <td className="table-td text-right font-semibold">{fmt(e.net_amount)}</td>
                  <td className="table-td text-xs text-gray-400">{e.financial_year} · {e.quarter}</td>
                  <td className="table-td">
                    {e.synced_to_erp
                      ? <span className="badge-green">Synced</span>
                      : <span className="badge-gray">Pending</span>
                    }
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
