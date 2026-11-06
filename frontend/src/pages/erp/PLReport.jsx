import { useState } from 'react'
import { erpAPI } from '../../services/api'
import toast from 'react-hot-toast'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
const pct = (n) => `${Number(n || 0).toFixed(2)}%`

function Row({ label, value, bold, indent }) {
  return (
    <div className={`flex justify-between py-2 border-b border-gray-100 text-sm ${bold ? 'font-bold text-gray-900' : 'text-gray-600'} ${indent ? 'pl-4' : ''}`}>
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  )
}

export default function PLReport() {
  const [fromDate, setFromDate] = useState('')
  const [toDate,   setToDate]   = useState('')
  const [report, setReport]     = useState(null)
  const [trial,  setTrial]      = useState(null)
  const [loading, setLoading]   = useState(false)
  const [activeTab, setActiveTab] = useState('pl')

  // Default to current Indian FY
  function setCurrentFY() {
    const now = new Date()
    const fyStart = now.getMonth() >= 3
      ? new Date(now.getFullYear(), 3, 1)      // Apr this year
      : new Date(now.getFullYear() - 1, 3, 1)  // Apr last year
    const fyEnd = new Date(fyStart.getFullYear() + 1, 2, 31)
    setFromDate(fyStart.toISOString().slice(0, 10))
    setToDate(Math.min(fyEnd, now) === fyEnd ? fyEnd.toISOString().slice(0, 10) : now.toISOString().slice(0, 10))
  }

  function currentFYLabel() {
    const now = new Date()
    return now.getMonth() >= 3
      ? `${now.getFullYear()}-${now.getFullYear() + 1}`
      : `${now.getFullYear() - 1}-${now.getFullYear()}`
  }

  async function fetchReports() {
    if (!fromDate || !toDate) { toast.error('Select both dates'); return }
    setLoading(true)
    try {
      const [pl, tb] = await Promise.all([
        erpAPI.getPL({ from_date: fromDate, to_date: toDate }),
        erpAPI.getTrialBalance({ financial_year: currentFYLabel() }),
      ])
      setReport(pl.data)
      setTrial(tb.data)
      toast.success('Reports loaded')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to generate report')
    } finally { setLoading(false) }
  }

  const monthlyData = report?.monthly_breakdown?.map(m => ({
    name: m.month,
    Invoiced:  Number(m.invoiced  || 0),
    Collected: Number(m.collected || 0),
  })) || []

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-gray-900">Financial Reports</h1>

      {/* Controls */}
      <div className="card p-5 flex flex-wrap items-end gap-3">
        <div>
          <label className="label">From Date</label>
          <input type="date" className="input w-40" value={fromDate} onChange={e => setFromDate(e.target.value)} />
        </div>
        <div>
          <label className="label">To Date</label>
          <input type="date" className="input w-40" value={toDate} onChange={e => setToDate(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={setCurrentFY}>Current FY</button>
          <button className="btn-primary" onClick={fetchReports} disabled={loading}>
            {loading ? 'Loading…' : 'Generate'}
          </button>
        </div>
      </div>

      {/* Tabs */}
      {(report || trial) && (
        <div className="flex gap-2">
          {['pl', 'trial'].map(t => (
            <button key={t} onClick={() => setActiveTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === t ? 'bg-blue-600 text-white' : 'bg-white border border-gray-300 text-gray-600 hover:bg-gray-50'}`}>
              {t === 'pl' ? 'Profit & Loss' : 'Trial Balance'}
            </button>
          ))}
        </div>
      )}

      {/* P&L Report */}
      {report && activeTab === 'pl' && (
        <div className="space-y-4">
          <div className="card p-6">
            <h2 className="font-semibold text-gray-800 mb-1">Profit & Loss Statement</h2>
            <p className="text-xs text-gray-400 mb-4">{report.period_label}</p>

            <div className="space-y-0">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Revenue</p>
              <Row label="Gross Invoiced"   value={fmt(report.gross_invoiced)} />
              <Row label="Less: Discounts"  value={`(${fmt(report.total_discount)})`} indent />
              <Row label="Less: Credit Notes Given" value={`(${fmt(Number(report.gross_invoiced) - Number(report.net_revenue) - Number(report.total_discount))})`} indent />
              <Row label="Net Revenue"      value={fmt(report.net_revenue)} bold />

              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4 mb-1">GST Collected (Liability)</p>
              <Row label="CGST Collected"  value={fmt(report.cgst_collected)} indent />
              <Row label="SGST Collected"  value={fmt(report.sgst_collected)} indent />
              <Row label="IGST Collected"  value={fmt(report.igst_collected)} indent />
              <Row label="Total Tax Collected" value={fmt(report.total_tax_collected)} />

              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4 mb-1">Collections</p>
              <Row label="Cash Collected"  value={fmt(report.total_collected)} />

              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4 mb-1">Purchases</p>
              <Row label="Total Purchases" value={fmt(report.total_purchases)} />
              <Row label="Purchase Tax Paid" value={fmt(report.total_purchase_tax_paid)} indent />

              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-4 mb-1">Profitability</p>
              <Row label="Gross Profit"   value={fmt(report.gross_profit)} bold />
              <Row label="Gross Margin"   value={pct(report.gross_profit_margin)} indent />
              <Row label="Bad Debts"      value={`(${fmt(report.bad_debts_written_off)})`} indent />
              <Row label="Net Profit"     value={fmt(report.net_profit)} bold />
              <Row label="Net Margin"     value={pct(report.net_profit_margin)} indent />
            </div>
          </div>

          {/* Monthly chart */}
          {monthlyData.length > 0 && (
            <div className="card p-6">
              <h3 className="font-semibold text-gray-800 mb-4">Monthly Breakdown</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={v => fmt(v)} />
                  <Legend />
                  <Bar dataKey="Invoiced"  fill="#3b82f6" radius={[4,4,0,0]} />
                  <Bar dataKey="Collected" fill="#10b981" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Trial Balance */}
      {trial && activeTab === 'trial' && (
        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="font-semibold text-gray-800">Trial Balance — FY {trial.financial_year}</h2>
              <p className="text-xs text-gray-400">As of {new Date(trial.as_of).toLocaleDateString('en-IN')}</p>
            </div>
            <span className={trial.is_balanced ? 'badge-green' : 'badge-red'}>
              {trial.is_balanced ? 'Balanced' : 'Imbalanced'}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50">
                  <th className="table-th">Entry Type</th>
                  <th className="table-th text-right">Debit</th>
                  <th className="table-th text-right">Credit</th>
                  <th className="table-th text-right">Net</th>
                </tr>
              </thead>
              <tbody>
                {trial.entries_by_type?.map(e => (
                  <tr key={e.entry_type} className="table-row">
                    <td className="table-td capitalize">{e.entry_type?.replace(/_/g, ' ')}</td>
                    <td className="table-td text-right">{fmt(e.debit)}</td>
                    <td className="table-td text-right">{fmt(e.credit)}</td>
                    <td className="table-td text-right font-semibold">{fmt(e.net)}</td>
                  </tr>
                ))}
                <tr className="bg-gray-50 font-bold">
                  <td className="table-td">Total</td>
                  <td className="table-td text-right">{fmt(trial.total_debits)}</td>
                  <td className="table-td text-right">{fmt(trial.total_credits)}</td>
                  <td className="table-td text-right">{fmt(trial.balance)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!report && !loading && (
        <div className="text-center py-16 text-gray-400 text-sm">
          Select a date range and click Generate to produce the report.
        </div>
      )}
    </div>
  )
}
