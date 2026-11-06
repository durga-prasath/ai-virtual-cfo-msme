import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import toast from 'react-hot-toast'

export default function Register() {
  const { register } = useAuth()
  const navigate     = useNavigate()
  const [form, setForm]       = useState({
    full_name: '', email: '', password: '',
    business_name: '', gstin: '',
  })
  const [loading, setLoading] = useState(false)

  const set = key => e => setForm(p => ({ ...p, [key]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      await register(form)
      toast.success('Account created! Welcome aboard.')
      navigate('/dashboard')
    } catch (err) {
      const detail = err.response?.data?.detail
      toast.error(Array.isArray(detail) ? detail[0]?.msg : (detail || 'Registration failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Create your account</h1>
          <p className="text-gray-500 mt-1">Free MSME CFO platform</p>
        </div>

        <div className="card p-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4">
              <div>
                <label className="label">Full name</label>
                <input type="text" required className="input" placeholder="Durga Prasath"
                  value={form.full_name} onChange={set('full_name')} />
              </div>
              <div>
                <label className="label">Email address</label>
                <input type="email" required className="input" placeholder="you@company.com"
                  value={form.email} onChange={set('email')} />
              </div>
              <div>
                <label className="label">Password</label>
                <input type="password" required className="input" placeholder="Min 8 characters"
                  value={form.password} onChange={set('password')} minLength={6} />
              </div>
              <div>
                <label className="label">Business name</label>
                <input type="text" required className="input" placeholder="Acme Pvt Ltd"
                  value={form.business_name} onChange={set('business_name')} />
              </div>
              <div>
                <label className="label">GSTIN <span className="text-gray-400 font-normal">(optional)</span></label>
                <input type="text" className="input" placeholder="22AAAAA0000A1Z5"
                  value={form.gstin} onChange={set('gstin')} maxLength={15} />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5 mt-2">
              {loading ? 'Creating account…' : 'Create account'}
            </button>
          </form>
          <p className="text-center text-sm text-gray-500 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-blue-600 hover:underline font-medium">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
