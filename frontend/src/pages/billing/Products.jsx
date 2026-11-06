import { useEffect, useState } from 'react'
import { billingAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon } from '@heroicons/react/24/outline'

export default function Products() {
  const [products, setProducts] = useState([])
  const [loading, setLoading]   = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', hsn_code: '', base_price: '', gst_rate: '18.00', unit: 'NOS', description: '' })
  const [saving, setSaving]     = useState(false)

  useEffect(() => { fetchProducts() }, [])

  async function fetchProducts() {
    try {
      const res = await billingAPI.getProducts()
      setProducts(res.data?.products || res.data || [])
    } catch { toast.error('Failed to load products') }
    finally { setLoading(false) }
  }

  async function handleCreate(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await billingAPI.createProduct({ ...form, base_price: parseFloat(form.base_price), gst_rate: parseFloat(form.gst_rate) })
      toast.success('Product added')
      setShowForm(false)
      setForm({ name: '', hsn_code: '', base_price: '', gst_rate: '18.00', unit: 'NOS', description: '' })
      fetchProducts()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create product')
    } finally { setSaving(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Products & Services</h1>
        <button className="btn-primary" onClick={() => setShowForm(p => !p)}>
          <PlusIcon className="w-4 h-4" /> Add Product
        </button>
      </div>

      {showForm && (
        <div className="card p-6">
          <h2 className="font-semibold mb-4">New Product / Service</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div><label className="label">Name *</label>
              <input required className="input" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></div>
            <div><label className="label">HSN / SAC Code</label>
              <input className="input" value={form.hsn_code} onChange={e => setForm(p => ({ ...p, hsn_code: e.target.value }))} /></div>
            <div><label className="label">Base Price (Rs.) *</label>
              <input required type="number" step="0.01" className="input" value={form.base_price}
                onChange={e => setForm(p => ({ ...p, base_price: e.target.value }))} /></div>
            <div><label className="label">GST Rate (%) *</label>
              <select className="input" value={form.gst_rate} onChange={e => setForm(p => ({ ...p, gst_rate: e.target.value }))}>
                {['0', '0.25', '5', '12', '18', '28'].map(r => <option key={r} value={r}>{r}%</option>)}
              </select></div>
            <div><label className="label">Unit</label>
              <input className="input" value={form.unit} onChange={e => setForm(p => ({ ...p, unit: e.target.value }))} /></div>
            <div className="flex items-end gap-2">
              <button type="submit" disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Save'}</button>
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
                <th className="table-th">Name</th>
                <th className="table-th">HSN Code</th>
                <th className="table-th text-right">Price</th>
                <th className="table-th text-right">GST</th>
                <th className="table-th">Unit</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-10 text-gray-400">Loading…</td></tr>
              ) : products.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-10 text-gray-400">No products yet</td></tr>
              ) : products.map(p => (
                <tr key={p.id} className="table-row">
                  <td className="table-td font-medium">{p.name}</td>
                  <td className="table-td font-mono text-xs text-gray-500">{p.hsn_code || '—'}</td>
                  <td className="table-td text-right">Rs. {Number(p.base_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                  <td className="table-td text-right">{Number(p.gst_rate)}%</td>
                  <td className="table-td text-gray-500">{p.unit || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
