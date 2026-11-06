import { NavLink } from 'react-router-dom'
import {
  HomeIcon, UsersIcon, CubeIcon, DocumentTextIcon,
  CreditCardIcon, CalculatorIcon, ShoppingCartIcon,
  ChartBarIcon, BellIcon, BuildingOfficeIcon,
  BookOpenIcon, PresentationChartLineIcon,
  ChatBubbleLeftRightIcon, DocumentMagnifyingGlassIcon, ArrowDownTrayIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'

const nav = [
  { label: 'Dashboard', to: '/dashboard', icon: HomeIcon },
  { label: 'AI CFO Chatbot', to: '/chatbot', icon: ChatBubbleLeftRightIcon },
  { label: 'Doc Scanner (OCR)', to: '/scanner', icon: DocumentMagnifyingGlassIcon },
  {
    label: 'Billing', icon: DocumentTextIcon, children: [
      { label: 'Customers',  to: '/billing/customers', icon: UsersIcon },
      { label: 'Products',   to: '/billing/products',  icon: CubeIcon },
      { label: 'Invoices',   to: '/billing/invoices',  icon: DocumentTextIcon },
      { label: 'Payments',   to: '/billing/payments',  icon: CreditCardIcon },
    ]
  },
  { label: 'GST Reports',  to: '/gst',        icon: CalculatorIcon },
  { label: 'Purchases',    to: '/purchases',   icon: ShoppingCartIcon },
  {
    label: 'Virtual CFO', icon: PresentationChartLineIcon, children: [
      { label: 'Cash Flow', to: '/cfo/forecast', icon: ChartBarIcon },
      { label: 'Alerts',    to: '/cfo/alerts',   icon: BellIcon },
    ]
  },
  {
    label: 'ERP & Ledger', icon: BuildingOfficeIcon, children: [
      { label: 'Tally XML Sync', to: '/erp/tally', icon: ArrowDownTrayIcon },
      { label: 'ERP Settings', to: '/erp/settings', icon: BuildingOfficeIcon },
      { label: 'Revenue Ledger', to: '/erp/ledger', icon: BookOpenIcon },
      { label: 'P&L Report',  to: '/erp/pl',       icon: PresentationChartLineIcon },
    ]
  },
]


function NavItem({ item, depth = 0 }) {
  if (item.children) {
    return (
      <div>
        <div className={clsx(
          'flex items-center gap-3 px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider mt-4',
          depth > 0 && 'pl-6'
        )}>
          <item.icon className="w-4 h-4" />
          {item.label}
        </div>
        {item.children.map(child => (
          <NavItem key={child.to} item={child} depth={depth + 1} />
        ))}
      </div>
    )
  }

  return (
    <NavLink
      to={item.to}
      className={({ isActive }) => clsx(
        'flex items-center gap-3 px-3 py-2 mx-2 rounded-lg text-sm transition-colors',
        depth > 0 && 'pl-8',
        isActive
          ? 'bg-blue-50 text-blue-700 font-medium'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      )}
    >
      <item.icon className="w-4 h-4 flex-shrink-0" />
      {item.label}
    </NavLink>
  )
}

export default function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2 px-5 h-16 border-b border-gray-200 flex-shrink-0">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <PresentationChartLineIcon className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold text-gray-900 leading-tight">AI Virtual CFO</p>
          <p className="text-xs text-gray-400">MSME Platform</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 space-y-0.5">
        {nav.map(item => (
          <NavItem key={item.label} item={item} />
        ))}
      </nav>

      {/* Version footer */}
      <div className="px-5 py-3 border-t border-gray-100">
        <p className="text-xs text-gray-400">Platform v0.8.0</p>
      </div>
    </aside>
  )
}
