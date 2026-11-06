import { useEffect, useState } from 'react'
import { alertsAPI } from '../../services/api'
import toast from 'react-hot-toast'
import { BellIcon, CheckIcon, XMarkIcon } from '@heroicons/react/24/outline'
import clsx from 'clsx'

const SEV_BADGE = { critical: 'badge-red', high: 'badge-yellow', medium: 'badge-blue', low: 'badge-gray' }
const SEV_BORDER = { critical: 'border-l-red-500', high: 'border-l-yellow-500', medium: 'border-l-blue-400', low: 'border-l-gray-300' }

export default function Alerts() {
  const [alerts, setAlerts]   = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [scanning, setScanning]     = useState(false)

  useEffect(() => { fetchAlerts() }, [unreadOnly])

  async function fetchAlerts() {
    setLoading(true)
    try {
      const [a, s] = await Promise.all([
        alertsAPI.list({ unread_only: unreadOnly }),
        alertsAPI.summary(),
      ])
      setAlerts(a.data || [])
      setSummary(s.data)
    } catch { toast.error('Failed to load alerts') }
    finally { setLoading(false) }
  }

  async function handleScan() {
    setScanning(true)
    try {
      const res = await alertsAPI.scan()
      toast.success(`${res.data.new_alerts_created} new alert(s) generated`)
      fetchAlerts()
    } catch { toast.error('Scan failed') }
    finally { setScanning(false) }
  }

  async function handleMarkAllRead() {
    try {
      await alertsAPI.markAllRead()
      toast.success('All alerts marked as read')
      fetchAlerts()
    } catch { toast.error('Failed') }
  }

  async function handleDismiss(id) {
    try {
      await alertsAPI.dismiss(id)
      setAlerts(a => a.filter(al => al.id !== id))
    } catch { toast.error('Failed to dismiss') }
  }

  async function handleMarkRead(id) {
    try {
      await alertsAPI.markRead({ alert_ids: [id] })
      setAlerts(a => a.map(al => al.id === id ? { ...al, is_read: true } : al))
    } catch {}
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Smart Alerts</h1>
          {summary && (
            <p className="text-sm text-gray-500 mt-0.5">
              {summary.total} total · {summary.unread} unread · {summary.critical} critical
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setUnreadOnly(p => !p)}
            className={clsx('btn-secondary text-sm', unreadOnly && 'bg-blue-50 text-blue-700 border-blue-300')}>
            {unreadOnly ? 'All Alerts' : 'Unread Only'}
          </button>
          <button onClick={handleMarkAllRead} className="btn-secondary text-sm">
            <CheckIcon className="w-4 h-4" /> Mark All Read
          </button>
          <button onClick={handleScan} disabled={scanning} className="btn-primary text-sm">
            <BellIcon className="w-4 h-4" />
            {scanning ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>
      </div>

      {/* Summary badges */}
      {summary && (
        <div className="flex gap-3 flex-wrap">
          {[
            { label: `${summary.critical} Critical`, cls: 'badge-red' },
            { label: `${summary.high} High`,        cls: 'badge-yellow' },
            { label: `${summary.medium} Medium`,    cls: 'badge-blue' },
            { label: `${summary.low} Low`,          cls: 'badge-gray' },
          ].map(b => <span key={b.label} className={b.cls}>{b.label}</span>)}
        </div>
      )}

      {/* Alert list */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <BellIcon className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>No alerts {unreadOnly ? 'unread' : 'found'}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map(alert => (
            <div
              key={alert.id}
              className={clsx(
                'card border-l-4 p-4 transition-opacity',
                SEV_BORDER[alert.severity] || 'border-l-gray-300',
                alert.is_read && 'opacity-70',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className={SEV_BADGE[alert.severity] || 'badge-gray'}>{alert.severity}</span>
                    <span className="badge-gray">{alert.alert_type?.replace(/_/g, ' ')}</span>
                    {!alert.is_read && <span className="w-2 h-2 bg-blue-500 rounded-full" />}
                  </div>
                  <p className="font-semibold text-gray-900 text-sm">{alert.title}</p>
                  <p className="text-sm text-gray-600 mt-0.5">{alert.message}</p>
                  {alert.recommendation && (
                    <p className="text-xs text-blue-600 mt-1">💡 {alert.recommendation}</p>
                  )}
                  <p className="text-xs text-gray-400 mt-2">
                    {alert.created_at ? new Date(alert.created_at).toLocaleString('en-IN') : ''}
                  </p>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  {!alert.is_read && (
                    <button onClick={() => handleMarkRead(alert.id)}
                      className="p-1.5 text-gray-400 hover:text-green-600 rounded-lg hover:bg-green-50"
                      title="Mark as read">
                      <CheckIcon className="w-4 h-4" />
                    </button>
                  )}
                  <button onClick={() => handleDismiss(alert.id)}
                    className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50"
                    title="Dismiss">
                    <XMarkIcon className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
