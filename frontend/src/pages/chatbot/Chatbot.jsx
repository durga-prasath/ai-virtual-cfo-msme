import { useState, useEffect, useRef } from 'react'
import { chatbotAPI } from '../../services/api'
import { Button, Badge, Card } from '../../components/ui'
import toast from 'react-hot-toast'
import {
  ChatBubbleLeftRightIcon,
  PaperAirplaneIcon,
  SparklesIcon,
  ArrowPathIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline'

export default function Chatbot() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Namaste! I am your AI Virtual CFO (CFO Mitra). I can analyze your financial performance, compute real-time GST liabilities, alert you to overdue customer balances, and track payments. How can I help your business today?',
      tools: [],
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [categories, setCategories] = useState({})
  const messagesEndRef = useRef(null)

  useEffect(() => {
    chatbotAPI.getSuggested()
      .then(res => setCategories(res.data?.categories || {}))
      .catch(() => {})
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend(textToSend) {
    const q = (textToSend || input).trim()
    if (!q) return

    const userMsg = { role: 'user', content: q }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    try {
      const history = nextMessages
        .filter(m => m.role === 'user' || m.role === 'assistant')
        .slice(-10)

      const res = await chatbotAPI.ask({
        query: q,
        history: history.map(m => ({ role: m.role, content: m.content })),
      })

      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: res.data?.answer || 'Response completed.',
          tools: res.data?.tools_executed || [],
        }
      ])
    } catch (err) {
      toast.error('Failed to get answer from CFO Chatbot')
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an issue accessing financial records. Please ensure database connections are active.',
          tools: [],
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleChipClick(question) {
    handleSend(question)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)] max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0 bg-white p-4 rounded-xl border border-gray-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md">
            <ChatBubbleLeftRightIcon className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-gray-900 leading-tight">AI Virtual CFO (Gemini)</h1>
            <p className="text-xs text-gray-500">Autonomous Financial Intelligence with Read-Only DB Tool Calling</p>
          </div>
        </div>
        <Badge variant="success">Active Grounding</Badge>
      </div>

      {/* Main Chat Message List */}
      <div className="flex-1 overflow-y-auto bg-white border border-gray-200 rounded-xl p-6 space-y-4 shadow-sm">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-2xl rounded-2xl px-5 py-3.5 text-sm ${
                m.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-none shadow-sm'
                  : 'bg-gray-100 text-gray-900 rounded-bl-none border border-gray-200'
              }`}
            >
              {/* Tool Execution Tag */}
              {m.tools?.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {m.tools.map((t, tidx) => (
                    <span
                      key={tidx}
                      className="inline-flex items-center gap-1 text-[10px] font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200"
                    >
                      <WrenchScrewdriverIcon className="w-3 h-3" />
                      {t}()
                    </span>
                  ))}
                </div>
              )}

              <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-50 border border-gray-200 rounded-2xl rounded-bl-none px-4 py-3 flex items-center gap-2 text-xs text-gray-500">
              <SparklesIcon className="w-4 h-4 text-blue-600 animate-spin" />
              <span>CFO Mitra is analyzing financial ledger and executing queries...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Questions Chips */}
      {Object.keys(categories).length > 0 && (
        <div className="flex-shrink-0 overflow-x-auto pb-1 flex gap-2">
          {Object.entries(categories).flatMap(([cat, qs]) =>
            qs.slice(0, 1).map((q, qidx) => (
              <button
                key={`${cat}-${qidx}`}
                onClick={() => handleChipClick(q)}
                disabled={loading}
                className="text-xs bg-white hover:bg-blue-50 hover:text-blue-700 text-gray-600 px-3 py-1.5 rounded-full border border-gray-200 shadow-sm whitespace-nowrap transition-colors flex-shrink-0"
              >
                {q}
              </button>
            ))
          )}
        </div>
      )}

      {/* Input Form */}
      <form
        onSubmit={e => {
          e.preventDefault()
          handleSend()
        }}
        className="flex gap-2 flex-shrink-0"
      >
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask CFO Mitra about sales, GST, invoices, top customers, or cashflow..."
          className="flex-1 px-4 py-3 text-sm bg-white border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm"
          disabled={loading}
        />
        <Button type="submit" loading={loading} className="px-5 rounded-xl">
          <PaperAirplaneIcon className="w-5 h-5" />
        </Button>
      </form>
    </div>
  )
}
