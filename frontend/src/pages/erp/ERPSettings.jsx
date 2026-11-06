import { useEffect, useState } from 'react'
import { erpAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { ArrowPathIcon } from '@heroicons/react/24/outline'

export default function ERPSettings() {
  const [biz, setBiz]       = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [form, setForm]       = useState({})
  const [syncResult, setSyncResult] = useState(null)

  useEffect(() => {
    Promise.all([erpAPI.getBusiness(), erpAPI.getConfig()])
      .then(([b, c]) => { setBiz(b.data); setConfig(c.data); setForm(b.data) })
      .catch(() => toast.error('Failed to load ERP settings'))
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await erpAPI.updateBusiness({
        business_name: form.business_name,
        gstin: form.gstin,
        pan: form.pan,
        email: form.email,
        phone: form.phone,
        city: form.city,
        state: form.state,
        pincode: form.pincode,
        address_line1: form.address_line1,
        bank_name: form.bank_name,
        bank_account_number: form.bank_account_number,
        bank_ifsc: form.bank_ifsc,
        upi_id: form.upi_id,
        erp_enabled: form.erp_enabled,
        erp_provider: form.erp_provider,
      })
      setBiz(updated.data)
      toast.success('Business profile updated')
    } catch (err) { toast.error(err.response?.data?.detail || 'Save failed') }
    finally { setSaving(false) }
  }

  async function handleSync(dryRun) {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await erpAPI.sync({ provider: form.erp_provider || 'internal', direction: 'push', entities: ['all'], dry_run: dryRun })
      setSyncResult(res.data)
      if (!dryRun) toast.success(res.data.message)
      else toast.success(`Dry run: ${res.data.entities.reduce((a, e) => a + e.total, 0)} records would sync`)
    } catch (err) { toast.error(err.response?.data?.detail || 'Sync failed') }
    finally { setSyncing(false) }
  }

  if (loading) return <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" /></div>

  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-xl font-bold text-gray-900">ERP & Business Settings</h1>

      {/* ERP Status */}
      {config && (
        <div className="card p-5 flex items-center justify-between flex-wrap gap-4">
          <div>
            <p className="text-sm font-semibold text-gray-700">ERP Status</p>
            <p className="text-xs text-gray-400 mt-0.5">
              {config.connection_status === 'connected' ? '🟢 Connected' : '⚪ Not configured'} · {config.erp_provider || '—'} · {config.pending_sync_count} pending
            </p>
            {config.erp_last_sync && (
              <p className="text-xs text-gray-400">Last sync: {new Date(config.erp_last_sync).toLocaleString('en-IN')}</p>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleSync(true)} disabled={syncing} className="btn-secondary text-sm">
              <ArrowPathIcon className="w-4 h-4" /> Dry Run
            </button>
            <button onClick={() => handleSync(false)} disabled={syncing} className="btn-primary text-sm">
              <ArrowPathIcon className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Syncing…' : 'Sync Now'}
            </button>
          </div>
        </div>
      )}

      {/* Sync result */}
      {syncResult && (
        <div className="card p-5 bg-blue-50 border-blue-200">
          <p className="font-semibold text-blue-800 mb-2">{syncResult.dry_run ? 'Dry Run Result' : 'Sync Complete'}</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {syncResult.entities?.map(e => (
              <div key={e.entity} className="text-sm">
                <p className="font-medium text-blue-700 capitalize">{e.entity}</p>
                <p className="text-blue-600">{e.total} total · {syncResult.dry_run ? e.total + ' to sync' : `${e.synced} synced`}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Business form */}
      <form onSubmit={handleSave} className="card p-6 space-y-5">
        <h2 className="font-semibold text-gray-800">Business Profile</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { label: 'Business Name', key: 'business_name' },
            { label: 'GSTIN', key: 'gstin' },
            { label: 'PAN', key: 'pan' },
            { label: 'Email', key: 'email', type: 'email' },
            { label: 'Phone', key: 'phone' },
            { label: 'City', key: 'city' },
            { label: 'State', key: 'state' },
            { label: 'Pincode', key: 'pincode' },
          ].map(f => (
            <div key={f.key}>
              <label className="label">{f.label}</label>
              <input type={f.type || 'text'} className="input" value={form[f.key] || ''}
                onChange={set(f.key)} />
            </div>
          ))}
          <div className="sm:col-span-2">
            <label className="label">Address</label>
            <input className="input" value={form.address_line1 || ''} onChange={set('address_line1')} />
          </div>
        </div>

        <h2 className="font-semibold text-gray-800 pt-2">Banking</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { label: 'Bank Name', key: 'bank_name' },
            { label: 'Account Number', key: 'bank_account_number' },
            { label: 'IFSC Code', key: 'bank_ifsc' },
            { label: 'UPI ID', key: 'upi_id' },
          ].map(f => (
            <div key={f.key}>
              <label className="label">{f.label}</label>
              <input className="input" value={form[f.key] || ''} onChange={set(f.key)} />
            </div>
          ))}
        </div>

        <h2 className="font-semibold text-gray-800 pt-2">ERP Configuration</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
          <div>
            <label className="label">ERP Provider</label>
            <select className="input" value={form.erp_provider || 'internal'} onChange={set('erp_provider')}>
              <option value="internal">Internal Only (no ERP)</option>
              <option value="tally">Tally Prime</option>
              <option value="zoho">Zoho Books</option>
              <option value="busy">Busy</option>
              <option value="marg">Marg</option>
            </select>
          </div>
          <div className="flex items-center gap-3 pt-5">
            <input type="checkbox" id="erp_enabled" className="w-4 h-4 rounded"
              checked={!!form.erp_enabled} onChange={set('erp_enabled')} />
            <label htmlFor="erp_enabled" className="text-sm font-medium text-gray-700">ERP Sync Enabled</label>
          </div>
        </div>

        <button type="submit" disabled={saving} className="btn-primary">
          {saving ? 'Saving…' : 'Save Changes'}
        </button>
      </form>
    </div>
  )
}
