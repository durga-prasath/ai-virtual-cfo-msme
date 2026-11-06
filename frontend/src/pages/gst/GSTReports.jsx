import { useState } from 'react'
import { gstAPI } from '../../services/api'
import toast from 'react-hot-toast'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`

function Section({ title, data }) {
  if (!data) return null
  return (
    <div className="card">
      <div className="card-header"><h2 className="font-semibold text-gray-800">{title}</h2></div>
      <div className="card-body">
        <pre className="text-xs text-gray-600 whitespace-pre-wrap overflow-x-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  )
}

export default function GSTReports() {
  const [period, setPeriod]   = useState(new Date().toISOString().slice(0, 7)) // YYYY-MM
  const [report, setReport]   = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('gstr3b')

  async function fetchReport() {
    setLoading(true)
    setReport(null)
    const [year, month] = period.split('-')
    const return_period = `${month.padStart(2, '0')}-${year}`
    const params = { return_period, month: parseInt(month), year: parseInt(year) }
    try {
      let res
      if (activeTab === 'gstr1')   res = await gstAPI.gstr1(params)
      if (activeTab === 'gstr3b')  res = await gstAPI.gstr3b(params)
      if (activeTab === 'liability') res = await gstAPI.liability(params)
      setReport(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to generate report')
    } finally { setLoading(false) }
  }


  const tabs = [
    { id: 'gstr3b', label: 'GSTR-3B' },
    { id: 'gstr1',  label: 'GSTR-1' },
    { id: 'liability', label: 'Tax Liability' },
  ]

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-gray-900">GST Reports</h1>

      {/* Controls */}
      <div className="card p-5 flex flex-wrap items-end gap-4">
        <div>
          <label className="label">Return Period</label>
          <input type="month" className="input w-44" value={period}
            onChange={e => setPeriod(e.target.value)} />
        </div>
        <div className="flex gap-2">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === t.id ? 'bg-blue-600 text-white' : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}>
              {t.label}
            </button>
          ))}
        </div>
        <button className="btn-primary" onClick={fetchReport} disabled={loading}>
          {loading ? 'Generating…' : 'Generate Report'}
        </button>
      </div>

      {/* GSTR-3B summary */}
      {report && activeTab === 'gstr3b' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Total Tax Payable', val: fmt(report.total_tax_payable) },
              { label: 'CGST',   val: fmt(report.cgst_payable) },
              { label: 'SGST',   val: fmt(report.sgst_payable) },
              { label: 'IGST',   val: fmt(report.igst_payable) },
            ].map(s => (
              <div key={s.label} className="stat-card">
                <span className="text-xs text-gray-500">{s.label}</span>
                <span className="text-lg font-bold text-gray-900">{s.val}</span>
              </div>
            ))}
          </div>
          <Section title="Full GSTR-3B Data" data={report} />
        </div>
      )}

      {report && activeTab !== 'gstr3b' && (
        <Section title={`${tabs.find(t => t.id === activeTab)?.label} Data`} data={report} />
      )}

      {!report && !loading && (
        <div className="text-center py-16 text-gray-400 text-sm">
          Select a period and report type, then click Generate Report.
        </div>
      )}
    </div>
  )
}
