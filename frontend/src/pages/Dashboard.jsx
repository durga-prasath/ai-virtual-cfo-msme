import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar, Legend,
} from 'recharts'
import { cfoAPI, alertsAPI } from '../services/api'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const fmt = (n) => `Rs. ${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
const pct = (n) => `${Number(n || 0).toFixed(1)}%`

function StatCard({ label, value, sub, color = 'blue' }) {
  const colors = {
    blue:   'bg-blue-50 text-blue-700',
    green:  'bg-green-50 text-green-700',
    red:    'bg-red-50 text-red-700',
    yellow: 'bg-yellow-50 text-yellow-700',
    purple: 'bg-purple-50 text-purple-700',
  }
  return (
    <div className="stat-card">
      <span className={clsx('text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full w-fit', colors[color])}>
        {label}
      </span>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-sm text-gray-400">{sub}</p>}
    </div>
  )
}

function AgingTable({ buckets = [] }) {
  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Receivables Aging</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50">
              <th className="table-th">Bucket</th>
              <th className="table-th text-right">Amount</th>
              <th className="table-th text-right">Invoices</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map(b => (
              <tr key={b.bucket} className="table-row">
                <td className="table-td font-medium">{b.bucket}</td>
                <td className="table-td text-right">{fmt(b.amount)}</td>
                <td className="table-td text-right">{b.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [dash, setDash]       = useState(null)
  const [alertSum, setAlertSum] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      cfoAPI.getDashboard(),
      alertsAPI.summary(),
    ])
      .then(([d, a]) => {
        setDash(d.data)
        setAlertSum(a.data)
      })
      .catch(() => toast.error('Failed to load dashboard'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (!dash) return null

  const monthly = (dash.monthly_revenue || []).slice(-6)

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Virtual CFO Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">As of {dash.as_of ? new Date(dash.as_of).toLocaleDateString('en-IN') : '—'}</p>
        </div>
        {alertSum?.critical > 0 && (
          <button
            onClick={() => navigate('/cfo/alerts')}
            className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-700 rounded-lg text-sm font-medium hover:bg-red-100 transition-colors"
          >
            <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
            {alertSum.critical} Critical Alert{alertSum.critical > 1 ? 's' : ''}
          </button>
        )}
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          label="Revenue YTD"
          value={fmt(dash.total_revenue_ytd)}
          sub={`${pct(dash.revenue_collected_percent)} collected`}
          color="green"
        />
        <StatCard
          label="Outstanding Receivables"
          value={fmt(dash.total_outstanding_receivables)}
          sub={`${fmt(dash.overdue_receivables)} overdue`}
          color="yellow"
        />
        <StatCard
          label="GST Payable"
          value={fmt(dash.gst_payable_current_month)}
          sub={`Due ${dash.gst_due_date}`}
          color="purple"
        />
        <StatCard
          label="Net Cash Position"
          value={fmt(dash.net_cash_position)}
          sub={dash.cash_runway_months != null
            ? `${Number(dash.cash_runway_months).toFixed(1)} months runway`
            : 'No outflows recorded'}
          color={Number(dash.net_cash_position) > 0 ? 'blue' : 'red'}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Monthly Revenue */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold text-gray-800">Monthly Revenue Trend</h2>
          </div>
          <div className="card-body">
            {monthly.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={monthly} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="inv" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="col" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => fmt(v)} />
                  <Legend />
                  <Area type="monotone" dataKey="invoiced"  stroke="#3b82f6" fill="url(#inv)" name="Invoiced"  />
                  <Area type="monotone" dataKey="collected" stroke="#10b981" fill="url(#col)" name="Collected" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-44 flex items-center justify-center text-gray-400 text-sm">
                No revenue data yet
              </div>
            )}
          </div>
        </div>

        {/* Receivables Aging */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold text-gray-800">Receivables Aging</h2>
          </div>
          <div className="card-body">
            {dash.receivables_aging?.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={dash.receivables_aging} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => fmt(v)} />
                  <Bar dataKey="amount" fill="#f59e0b" name="Amount" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-44 flex items-center justify-center text-gray-400 text-sm">
                No receivables data
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Obligations */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold text-gray-800">Next 30 Days</h2>
          </div>
          <div className="card-body space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Sales invoices due</span>
              <span className="font-semibold">{fmt(dash.invoices_due_next_30_days)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Purchase payments due</span>
              <span className="font-semibold">{fmt(dash.purchases_due_next_30_days)}</span>
            </div>
            <div className="flex justify-between text-sm border-t pt-3 mt-1">
              <span className="font-medium text-gray-700">Total obligations</span>
              <span className="font-bold text-gray-900">{fmt(dash.total_due_next_30_days)}</span>
            </div>
          </div>
        </div>

        {/* Alert Summary */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold text-gray-800">Alert Summary</h2>
            <button onClick={() => navigate('/cfo/alerts')} className="text-xs text-blue-600 hover:underline">
              View all
            </button>
          </div>
          <div className="card-body space-y-2">
            {[
              { label: 'Critical', val: dash.critical_alerts_count, cls: 'badge-red' },
              { label: 'High',     val: alertSum?.high    || 0, cls: 'badge-yellow' },
              { label: 'Medium',   val: alertSum?.medium  || 0, cls: 'badge-blue' },
              { label: 'Unread',   val: alertSum?.unread  || 0, cls: 'badge-gray' },
            ].map(r => (
              <div key={r.label} className="flex items-center justify-between text-sm">
                <span className={`badge ${r.cls}`}>{r.label}</span>
                <span className="font-semibold">{r.val}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Payables */}
        <div className="card">
          <div className="card-header">
            <h2 className="font-semibold text-gray-800">Payables</h2>
          </div>
          <div className="card-body space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Total outstanding</span>
              <span className="font-semibold">{fmt(dash.total_outstanding_payables)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Overdue</span>
              <span className="font-semibold text-red-600">{fmt(dash.overdue_payables)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
