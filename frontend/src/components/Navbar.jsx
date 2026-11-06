import { useNavigate } from 'react-router-dom'
import { BellIcon, ArrowRightOnRectangleIcon, UserCircleIcon } from '@heroicons/react/24/outline'
import { useAuth } from '../context/AuthContext'
import toast from 'react-hot-toast'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    toast.success('Logged out successfully')
    navigate('/login')
  }

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0">
      {/* Left — breadcrumb placeholder */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <span className="font-semibold text-gray-900">
          {user?.business_name || 'My Business'}
        </span>
      </div>

      {/* Right — user + logout */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/cfo/alerts')}
          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-900 transition-colors"
          title="Alerts"
        >
          <BellIcon className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 text-sm">
          <UserCircleIcon className="w-6 h-6 text-gray-400" />
          <div className="leading-tight">
            <p className="font-medium text-gray-900 text-sm">{user?.full_name}</p>
            <p className="text-xs text-gray-400">{user?.email}</p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors"
          title="Logout"
        >
          <ArrowRightOnRectangleIcon className="w-5 h-5" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </header>
  )
}
