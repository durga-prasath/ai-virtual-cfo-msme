import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { billingAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline'

export default function CreateInvoice() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState([])
  const [products,  setProducts]  = useState([])
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)

  const [form, setForm] = useState({
    customer_id: '',
    gst_type: 'INTRA',
    due_date: '',
    notes: '',
    items: [{ product_id: '', quantity: 1, unit_price: '' }],
  })

  useEffect(() => {
    Promise.all([billingAPI.getCustomers(), billingAPI.getProducts()])
      .then(([c, p]) => {
        setCustomers(c.data?.customers || c.data || [])
        setProducts(p.data?.products   || p.data || [])
      })
      .catch(() => toast.error('Failed to load form data'))
      .finally(() => setLoading(false))
  }, [])

  function addItem() {
    setForm(p => ({ ...p, items: [...p.items, { product_id: '', quantity: 1, unit_price: '' }] }))
  }
  function removeItem(i) {
    setForm(p => ({ ...p, items: p.items.filter((_, idx) => idx !== i) }))
  }
  function setItem(i, key, val) {
    setForm(p => {
      const items = [...p.items]
      items[i] = { ...items[i], [key]: val }
      // Auto-fill unit_price from product
      if (key === 'product_id') {
        const prod = products.find(pr => pr.id === val)
        if (prod) items[i].unit_price = prod.base_price
      }
      return { ...p, items }
    })
  }

  // Compute totals
  const totals = form.items.reduce((acc, item) => {
    const prod = products.find(p => p.id === item.product_id)
    const sub = Number(item.quantity || 0) * Number(item.unit_price || 0)
    const gst = prod ? sub * Number(prod.gst_rate) / 100 : 0
    return { subtotal: acc.subtotal + sub, tax: acc.tax + gst, total: acc.total + sub + gst }
  }, { subtotal: 0, tax: 0, total: 0 })

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.customer_id) return toast.error('Please select a customer')
    if (form.items.some(it => !it.product_id || !it.unit_price)) return toast.error('Complete all line items')
    setSaving(true)
    try {
      const payload = {
        ...form,
        items: form.items.map(it => ({
          product_id: it.product_id,
          quantity: Number(it.quantity),
          unit_price: String(it.unit_price),
        })),
      }
      await billingAPI.createInvoice(payload)
      toast.success('Invoice created!')
      navigate('/billing/invoices')
    } catch (err) {
      const d = err.response?.data?.detail
      toast.error(Array.isArray(d) ? d[0]?.msg : (d || 'Failed to create invoice'))
    } finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" /></div>

  const fmtCur = n => `Rs. ${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-gray-700">←</button>
        <h1 className="text-xl font-bold text-gray-900">New Invoice</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Header */}
        <div className="card p-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Customer *</label>
            <select required className="input" value={form.customer_id}
              onChange={e => setForm(p => ({ ...p, customer_id: e.target.value }))}>
              <option value="">Select customer…</option>
              {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label">GST Type</label>
            <select className="input" value={form.gst_type}
              onChange={e => setForm(p => ({ ...p, gst_type: e.target.value }))}>
              <option value="INTRA">INTRA (CGST + SGST)</option>
              <option value="INTER">INTER (IGST)</option>
            </select>
          </div>
          <div>
            <label className="label">Due Date *</label>
            <input required type="date" className="input" value={form.due_date}
              onChange={e => setForm(p => ({ ...p, due_date: e.target.value }))} />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Notes</label>
            <input className="input" placeholder="Optional payment terms…" value={form.notes}
              onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} />
          </div>
        </div>

        {/* Line items */}
        <div className="card p-6">
          <h2 className="font-semibold text-gray-800 mb-4">Line Items</h2>
          <div className="space-y-3">
            {form.items.map((item, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-5">
                  {i === 0 && <label className="label">Product</label>}
                  <select className="input" value={item.product_id}
                    onChange={e => setItem(i, 'product_id', e.target.value)}>
                    <option value="">Select…</option>
                    {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  {i === 0 && <label className="label">Qty</label>}
                  <input type="number" min={1} className="input" value={item.quantity}
                    onChange={e => setItem(i, 'quantity', e.target.value)} />
                </div>
                <div className="col-span-3">
                  {i === 0 && <label className="label">Unit Price</label>}
                  <input type="number" step="0.01" className="input" value={item.unit_price}
                    onChange={e => setItem(i, 'unit_price', e.target.value)} />
                </div>
                <div className="col-span-2 flex items-end gap-1">
                  {form.items.length > 1 && (
                    <button type="button" onClick={() => removeItem(i)}
                      className="p-2 text-red-400 hover:text-red-600">
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <button type="button" onClick={addItem}
            className="mt-4 flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800">
            <PlusIcon className="w-4 h-4" /> Add line item
          </button>
        </div>

        {/* Totals */}
        <div className="card p-6">
          <div className="flex flex-col items-end gap-1 text-sm">
            <div className="flex gap-8 text-gray-500">
              <span>Subtotal</span><span className="w-32 text-right">{fmtCur(totals.subtotal)}</span>
            </div>
            <div className="flex gap-8 text-gray-500">
              <span>GST</span><span className="w-32 text-right">{fmtCur(totals.tax)}</span>
            </div>
            <div className="flex gap-8 font-bold text-gray-900 text-base border-t pt-2 mt-1">
              <span>Total</span><span className="w-32 text-right">{fmtCur(totals.total)}</span>
            </div>
          </div>
        </div>

        <div className="flex gap-3 justify-end">
          <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>Cancel</button>
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? 'Creating…' : 'Create Invoice'}
          </button>
        </div>
      </form>
    </div>
  )
}
