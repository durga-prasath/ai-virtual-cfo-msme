import { useState, useEffect } from 'react'
import { erpAPI } from '../../services/api'
import { Button, Badge, Card } from '../../components/ui'
import toast from 'react-hot-toast'
import {
  ArrowDownTrayIcon,
  DocumentTextIcon,
  ShoppingCartIcon,
  CreditCardIcon,
  CheckBadgeIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline'

export default function TallySync() {
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState({})

  useEffect(() => {
    fetchSummary()
  }, [])

  function fetchSummary() {
    setLoading(true)
    erpAPI.getTallySummary()
      .then(res => setSummary(res.data))
      .catch(() => toast.error('Failed to load Tally sync summary'))
      .finally(() => setLoading(false))
  }

  async function handleDownload(type, apiFn, filename) {
    setDownloading(prev => ({ ...prev, [type]: true }))
    try {
      const res = await apiFn()
      const blob = new Blob([res.data], { type: 'application/xml' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success(`${filename} exported successfully`)
    } catch (err) {
      toast.error(`Failed to export ${type} XML`)
    } finally {
      setDownloading(prev => ({ ...prev, [type]: false }))
    }
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ArrowDownTrayIcon className="w-7 h-7 text-blue-600" />
            Tally XML Sync & Export
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Generate native Tally Prime & Tally.ERP 9 XML vouchers (<span className="font-mono text-xs">&lt;ENVELOPE&gt;</span> format) with exact ledger mapping.
          </p>
        </div>
        <Badge variant="success">Phase 9 Active</Badge>
      </div>

      {/* Info Callout */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-start gap-3">
        <InformationCircleIcon className="w-6 h-6 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-900 leading-relaxed">
          <p className="font-semibold text-sm mb-1">How to import into Tally Prime:</p>
          <ol className="list-decimal list-inside space-y-1 text-blue-800">
            <li>Download the relevant XML file below (Sales, Purchases, or Receipts).</li>
            <li>In Tally Prime, navigate to <strong>Alt+O (Import)</strong> → <strong>Transactions</strong>.</li>
            <li>Select XML format and specify the downloaded file path. Tally will import vouchers directly.</li>
          </ol>
        </div>
      </div>

      {/* Export Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Sales Vouchers */}
        <Card
          title="Sales Vouchers"
          subtitle="Outward invoices issued to customers"
          action={
            <span className="text-lg font-bold text-blue-600">
              {summary?.exportable_sales_invoices || 0}
            </span>
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              Debits Sundry Debtors, credits Sales Account, and allocates Output CGST/SGST/IGST ledgers.
            </p>
            <Button
              className="w-full"
              loading={downloading.sales}
              onClick={() =>
                handleDownload('sales', erpAPI.exportInvoicesXml, 'tally_sales_vouchers.xml')
              }
            >
              <DocumentTextIcon className="w-4 h-4 mr-2" />
              Download Sales XML
            </Button>
          </div>
        </Card>

        {/* Purchase Vouchers */}
        <Card
          title="Purchase Vouchers"
          subtitle="Vendor bills & inward supplies"
          action={
            <span className="text-lg font-bold text-blue-600">
              {summary?.exportable_purchase_invoices || 0}
            </span>
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              Credits Sundry Creditors, debits Purchase Account, and allocates Input CGST/SGST/IGST.
            </p>
            <Button
              className="w-full"
              variant="secondary"
              loading={downloading.purchases}
              onClick={() =>
                handleDownload('purchases', erpAPI.exportPurchasesXml, 'tally_purchase_vouchers.xml')
              }
            >
              <ShoppingCartIcon className="w-4 h-4 mr-2" />
              Download Purchase XML
            </Button>
          </div>
        </Card>

        {/* Receipt Vouchers */}
        <Card
          title="Receipt Vouchers"
          subtitle="Customer payments received"
          action={
            <span className="text-lg font-bold text-blue-600">
              {summary?.exportable_receipt_payments || 0}
            </span>
          }
        >
          <div className="space-y-4">
            <p className="text-xs text-gray-500">
              Debits Bank Account or Cash ledger, and credits Sundry Debtors customer account.
            </p>
            <Button
              className="w-full"
              variant="secondary"
              loading={downloading.payments}
              onClick={() =>
                handleDownload('payments', erpAPI.exportPaymentsXml, 'tally_receipt_vouchers.xml')
              }
            >
              <CreditCardIcon className="w-4 h-4 mr-2" />
              Download Receipt XML
            </Button>
          </div>
        </Card>
      </div>

      {/* Specifications Card */}
      <Card title="Tally Schema Standard Specifications">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div className="p-3 bg-gray-50 rounded-lg">
            <span className="font-semibold text-gray-700 block">Date Convention</span>
            <span className="text-gray-500 font-mono">YYYYMMDD strictly</span>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <span className="font-semibold text-gray-700 block">Root Envelope</span>
            <span className="text-gray-500 font-mono">&lt;ENVELOPE&gt;&lt;BODY&gt;</span>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <span className="font-semibold text-gray-700 block">Deduplication</span>
            <span className="text-gray-500 font-mono">REMOTEID (UUID)</span>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <span className="font-semibold text-gray-700 block">Sign Convention</span>
            <span className="text-gray-500 font-mono">ISDEEMEDPOSITIVE</span>
          </div>
        </div>
      </Card>
    </div>
  )
}
