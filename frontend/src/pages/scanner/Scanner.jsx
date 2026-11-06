import { useState, useEffect } from 'react'
import { ocrAPI, purchasesAPI } from '../../services/api'
import { Button, Badge, Card } from '../../components/ui'
import toast from 'react-hot-toast'
import {
  DocumentMagnifyingGlassIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'

export default function Scanner() {
  const [stage, setStage] = useState('idle') // idle | uploading | preview | confirmed
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [scanResult, setScanResult] = useState(null)
  const [supportedTypes, setSupportedTypes] = useState([])
  const [formData, setFormData] = useState({})

  useEffect(() => {
    ocrAPI.getSupportedTypes()
      .then(res => setSupportedTypes(res.data?.supported_types || []))
      .catch(() => {})
  }, [])

  function handleFileSelect(e) {
    const selected = e.target.files?.[0]
    if (!selected) return
    setFile(selected)
    setStage('idle')
    setScanResult(null)
  }

  async function handleScan() {
    if (!file) {
      toast.error('Please select a file first')
      return
    }
    setLoading(true)
    setStage('uploading')

    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await ocrAPI.scan(fd)
      setScanResult(res.data)
      
      // Initialize form with detected values
      const initial = {}
      if (res.data.fields) {
        Object.entries(res.data.fields).forEach(([k, v]) => {
          initial[k] = v.value || ''
        })
      }
      setFormData(initial)
      setStage('preview')
      toast.success(`Classified as ${res.data.document_type.replace('_', ' ')}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Document processing failed')
      setStage('idle')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm() {
    setLoading(true)
    try {
      const payload = {
        document_type: scanResult.document_type,
        confirmed_fields: formData,
        notes: `Confirmed from Scanner (${file?.name})`,
      }
      const res = await ocrAPI.confirm(payload)
      toast.success(res.data?.message || 'Document confirmed and posted!')
      setStage('confirmed')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save confirmed document')
    } finally {
      setLoading(false)
    }
  }

  function handleReset() {
    setFile(null)
    setScanResult(null)
    setFormData({})
    setStage('idle')
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <DocumentMagnifyingGlassIcon className="w-7 h-7 text-blue-600" />
            Smart Document Scanner
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            OpenCV preprocessed OCR with automatic classification (Bills, Invoices, Receipts, Salary Slips).
          </p>
        </div>
        <Badge variant="info">Phase 6 Active</Badge>
      </div>

      {/* Upload Zone */}
      {stage !== 'confirmed' && (
        <Card title="1. Upload Document" subtitle="Supports JPG, PNG, PDF files up to 10MB">
          <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-blue-500 transition-colors bg-gray-50">
            <ArrowUpTrayIcon className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <input
              type="file"
              id="file-input"
              className="hidden"
              accept=".jpg,.jpeg,.png,.pdf,.bmp"
              onChange={handleFileSelect}
            />
            <label
              htmlFor="file-input"
              className="cursor-pointer font-semibold text-blue-600 hover:text-blue-700 text-sm"
            >
              Click to browse file
            </label>
            <p className="text-xs text-gray-500 mt-1">
              {file ? file.name : 'PDF, PNG, JPG supported'}
            </p>
          </div>

          {file && (
            <div className="mt-4 flex items-center justify-between bg-blue-50 p-3 rounded-lg border border-blue-200">
              <span className="text-sm font-medium text-blue-800 truncate">{file.name}</span>
              <Button onClick={handleScan} loading={loading} size="sm">
                <SparklesIcon className="w-4 h-4 mr-1.5" />
                Run OCR & AI Classifier
              </Button>
            </div>
          )}
        </Card>
      )}

      {/* Preview and Verification Form */}
      {stage === 'preview' && scanResult && (
        <Card
          title="2. Review & Confirm Extracted Fields"
          subtitle={`Type: ${scanResult.document_type} | Confidence: ${scanResult.overall_confidence}% | Action: ${scanResult.suggested_action}`}
          action={
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={handleReset}>
                Cancel
              </Button>
              <Button variant="success" size="sm" onClick={handleConfirm} loading={loading}>
                <CheckCircleIcon className="w-4 h-4 mr-1.5" />
                Confirm & Post to Database
              </Button>
            </div>
          }
        >
          {scanResult.warnings?.length > 0 && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
              <ExclamationTriangleIcon className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-amber-800">
                {scanResult.warnings.map((w, idx) => (
                  <p key={idx}>{w}</p>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(scanResult.fields || {}).map(([key, item]) => (
              <div key={key}>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-gray-700 capitalize">
                    {key.replace(/_/g, ' ')}
                  </label>
                  <span className="text-[10px] text-gray-400 font-mono">
                    {item.confidence}% ({item.source})
                  </span>
                </div>
                <input
                  type="text"
                  value={formData[key] || ''}
                  onChange={e => setFormData({ ...formData, [key]: e.target.value })}
                  className="w-full text-sm px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white"
                />
              </div>
            ))}
          </div>

          {/* Raw Text Accordion Preview */}
          <div className="mt-6 pt-4 border-t border-gray-200">
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer font-medium text-gray-700">
                View Raw Preprocessed Text Preview ({scanResult.page_count} page(s))
              </summary>
              <pre className="mt-2 p-3 bg-gray-100 rounded-lg whitespace-pre-wrap font-mono text-[11px] max-h-48 overflow-y-auto">
                {scanResult.raw_text_preview || 'No raw text preview.'}
              </pre>
            </details>
          </div>
        </Card>
      )}

      {/* Confirmed State */}
      {stage === 'confirmed' && (
        <Card className="text-center py-12">
          <CheckCircleIcon className="w-16 h-16 text-emerald-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-900 mb-1">Document Confirmed & Saved!</h2>
          <p className="text-sm text-gray-500 max-w-md mx-auto mb-6">
            The document has been securely processed and written to the database. All amounts and ledger items have been updated.
          </p>
          <Button onClick={handleReset}>Scan Another Document</Button>
        </Card>
      )}

      {/* Supported Document Catalog */}
      <Card title="Supported Document Types" subtitle="All documents are preprocessed through OpenCV filters before OCR">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {supportedTypes.map(t => (
            <div key={t.type} className="p-3 border border-gray-200 rounded-lg bg-gray-50">
              <p className="text-sm font-semibold text-gray-900">{t.name}</p>
              <p className="text-xs text-gray-500 mt-1">{t.description}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
