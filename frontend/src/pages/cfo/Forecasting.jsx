import { useEffect, useState } from 'react'
import { cfoAPI } from '../../services/api'
import toast from 'react-hot-toast'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`

export default function Forecasting() {
  const [form, setForm] = useState({ forecast_type: 'monthly', scenario: 'baseline', periods_ahead: 3 })
  const [result, setResult]   = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => { fetchHistory() }, [])

  async function fetchHistory() {
    try {
      const res = await cfoAPI.listForecasts({ limit: 10 })
      setHistory(res.data || [])
    } catch {}
  }

  async function handleGenerate(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await cfoAPI.generateForecast({ ...form, periods_ahead: Number(form.periods_ahead) })
      setResult(res.data)
      toast.success('Forecast generated')
      fetchHistory()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Forecast failed')
    } finally { setLoading(false) }
  }

  const chartData = result?.periods?.map((p, i) => ({
    name: `Period ${i + 1}`,
    Inflow:  Number(p.predicted_inflow),
    Outflow: Number(p.predicted_outflow),
    Net:     Number(p.predicted_net),
  })) || []

  const SCENARIO_COLOR = { optimistic: 'text-green-600', baseline: 'text-blue-600', pessimistic: 'text-red-600' }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">Cash Flow Forecasting</h1>

      {/* Generator */}
      <div className="card p-6">
        <h2 className="font-semibold text-gray-800 mb-4">Generate Forecast</h2>
        <form onSubmit={handleGenerate} className="flex flex-wrap items-end gap-4">
          <div>
            <label className="label">Type</label>
            <select className="input w-36" value={form.forecast_type}
              onChange={e => setForm(p => ({ ...p, forecast_type: e.target.value }))}>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
          <div>
            <label className="label">Scenario</label>
            <select className="input w-40" value={form.scenario}
              onChange={e => setForm(p => ({ ...p, scenario: e.target.value }))}>
              <option value="baseline">Baseline</option>
              <option value="optimistic">Optimistic (+15%)</option>
              <option value="pessimistic">Pessimistic (-15%)</option>
            </select>
          </div>
          <div>
            <label className="label">Periods</label>
            <input type="number" min={1} max={12} className="input w-20" value={form.periods_ahead}
              onChange={e => setForm(p => ({ ...p, periods_ahead: e.target.value }))} />
          </div>
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Generating…' : 'Generate'}
          </button>
        </form>
      </div>

      {/* Result */}
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Total Inflow',  val: fmt(result.summary?.total_predicted_inflow) },
              { label: 'Total Outflow', val: fmt(result.summary?.total_predicted_outflow) },
              { label: 'Net Position',  val: fmt(result.summary?.total_predicted_net) },
              { label: 'Scenario',      val: result.scenario, className: SCENARIO_COLOR[result.scenario] },
            ].map(s => (
              <div key={s.label} className="stat-card">
                <span className="text-xs text-gray-500">{s.label}</span>
                <span className={`text-lg font-bold ${s.className || 'text-gray-900'}`}>{s.val}</span>
              </div>
            ))}
          </div>

          <div className="card p-6">
            <h3 className="font-semibold text-gray-800 mb-4">Forecast Chart</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                <Tooltip formatter={v => fmt(v)} />
                <Legend />
                <Line type="monotone" dataKey="Inflow"  stroke="#10b981" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="Outflow" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="Net"     stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Advisory */}
          {result.periods?.some(p => p.advisory_notes) && (
            <div className="card p-5 border-yellow-200 bg-yellow-50">
              <h3 className="font-semibold text-yellow-800 mb-2">CFO Advisory Notes</h3>
              <ul className="space-y-1">
                {result.periods.filter(p => p.advisory_notes).map((p, i) => (
                  <li key={i} className="text-sm text-yellow-700">• {p.advisory_notes}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="card">
          <div className="card-header"><h2 className="font-semibold text-gray-800">Recent Forecasts</h2></div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="table-th">Period</th>
                  <th className="table-th">Type</th>
                  <th className="table-th">Scenario</th>
                  <th className="table-th text-right">Net</th>
                  <th className="table-th text-right">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {history.map(h => (
                  <tr key={h.id} className="table-row">
                    <td className="table-td text-gray-500">{h.period_start?.slice(0,10)} → {h.period_end?.slice(0,10)}</td>
                    <td className="table-td">{h.forecast_type}</td>
                    <td className="table-td">
                      <span className={`badge ${h.scenario === 'optimistic' ? 'badge-green' : h.scenario === 'pessimistic' ? 'badge-red' : 'badge-blue'}`}>
                        {h.scenario}
                      </span>
                    </td>
                    <td className="table-td text-right font-medium">{fmt(h.predicted_net)}</td>
                    <td className="table-td text-right">{h.confidence_score ? `${(Number(h.confidence_score)*100).toFixed(0)}%` : '—'}</td>
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
