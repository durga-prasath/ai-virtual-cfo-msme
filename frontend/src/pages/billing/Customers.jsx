import { useEffect, useState } from 'react'
import { billingAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline'

export default function Customers() {
  const [customers, setCustomers] = useState([])
  const [loading, setLoading]     = useState(true)
  const [search, setSearch]       = useState('')
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm] = useState({ name: '', email: '', phone: '', gstin: '', state: '' })
  const [saving, setSaving]       = useState(false)

  useEffect(() => { fetchCustomers() }, [])

  async function fetchCustomers() {
    try {
      const res = await billingAPI.getCustomers()
      setCustomers(res.data?.customers || res.data || [])
    } catch { toast.error('Failed to load customers') }
    finally { setLoading(false) }
  }

  async function handleCreate(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, typeof v === 'string' && !v.trim() ? null : v.trim()])
      )
      await billingAPI.createCustomer(payload)
      toast.success('Customer added')
      setShowForm(false)
      setForm({ name: '', email: '', phone: '', gstin: '', state: '' })
      fetchCustomers()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create customer')
    } finally { setSaving(false) }
  }


  const filtered = customers.filter(c =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    (c.email || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Customers</h1>
        <button className="btn-primary" onClick={() => setShowForm(p => !p)}>
          <PlusIcon className="w-4 h-4" /> Add Customer
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="card p-6">
          <h2 className="font-semibold text-gray-800 mb-4">New Customer</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><label className="label">Name *</label>
              <input required className="input" value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></div>
            <div><label className="label">Email</label>
              <input type="email" className="input" value={form.email}
                onChange={e => setForm(p => ({ ...p, email: e.target.value }))} /></div>
            <div><label className="label">Phone</label>
              <input className="input" value={form.phone}
                onChange={e => setForm(p => ({ ...p, phone: e.target.value }))} /></div>
            <div><label className="label">GSTIN</label>
              <input className="input" maxLength={15} value={form.gstin}
                onChange={e => setForm(p => ({ ...p, gstin: e.target.value }))} /></div>
            <div><label className="label">State</label>
              <input className="input" value={form.state}
                onChange={e => setForm(p => ({ ...p, state: e.target.value }))} /></div>
            <div className="flex items-end gap-2">
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Search + table */}
      <div className="card">
        <div className="card-header">
          <div className="relative w-64">
            <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input className="input pl-9 py-1.5 text-sm" placeholder="Search customers…"
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          <span className="text-sm text-gray-500">{filtered.length} customer{filtered.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="table-th">Name</th>
                <th className="table-th">Email</th>
                <th className="table-th">GSTIN</th>
                <th className="table-th">State</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center py-10 text-gray-400">Loading…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-10 text-gray-400">No customers found</td></tr>
              ) : filtered.map(c => (
                <tr key={c.id} className="table-row">
                  <td className="table-td font-medium">{c.name}</td>
                  <td className="table-td text-gray-500">{c.email || '—'}</td>
                  <td className="table-td font-mono text-xs">{c.gstin || '—'}</td>
                  <td className="table-td">{c.state || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
