'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  const navigation = [
    { name: 'Overview', href: '/dashboard', icon: '📊' },
    {
      name: 'Reports',
      href: '/dashboard/reports',
      icon: '📋',
      children: [
        { name: 'All Reports', href: '/dashboard/reports' },
        { name: 'Fabric Reports', href: '/dashboard/reports/fabric' },
        { name: 'Sales Reports', href: '/dashboard/reports/sales' },
        { name: 'Inventory Analysis', href: '/dashboard/reports/inventory' },
        { name: 'Production Reports', href: '/dashboard/reports/production' },
      ],
    },
    {
      name: 'Raw Materials',
      href: '/dashboard/raw-materials',
      icon: '🧵',
      children: [
        { name: 'Yarn', href: '/dashboard/raw-materials/yarn' },
        { name: 'Fabric', href: '/dashboard/raw-materials/fabric' },
        { name: 'Processes', href: '/dashboard/raw-materials/processes' },
      ],
    },
    {
      name: 'Garments',
      href: '/dashboard/garments',
      icon: '👕',
      children: [
        { name: 'Master Data', href: '/dashboard/garments/master' },
        { name: 'Inventory', href: '/dashboard/garments/inventory' },
        { name: 'Production', href: '/dashboard/garments/production' },
      ],
    },
    {
      name: 'Sales',
      href: '/dashboard/sales',
      icon: '💰',
      children: [
        { name: 'Transactions', href: '/dashboard/sales/transactions' },
        { name: 'Panels', href: '/dashboard/sales/panels' },
        { name: 'Reports', href: '/dashboard/sales/reports' },
      ],
    },
    {
      name: 'Financial',
      href: '/dashboard/financial',
      icon: '📈',
      children: [
        { name: 'Discounts', href: '/dashboard/financial/discounts' },
        { name: 'Paid Ads', href: '/dashboard/financial/ads' },
        { name: 'ROI Analysis', href: '/dashboard/financial/roi' },
      ],
    },
  ];

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Top Navigation */}
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <Link href="/dashboard" className="text-2xl font-bold text-primary-600">
                Anthrilo
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <button className="text-gray-600 hover:text-gray-900">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
              </button>
              <button className="text-gray-600 hover:text-gray-900">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 bg-white shadow-md min-h-screen">
          <nav className="mt-5 px-2">
            {navigation.map((item) => (
              <div key={item.name}>
                <Link
                  href={item.href}
                  className={`group flex items-center px-2 py-2 text-base font-medium rounded-md ${
                    pathname === item.href
                      ? 'bg-primary-100 text-primary-900'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <span className="mr-3">{item.icon}</span>
                  {item.name}
                </Link>
                {item.children && (
                  <div className="ml-8 mt-1 space-y-1">
                    {item.children.map((child) => (
                      <Link
                        key={child.name}
                        href={child.href}
                        className={`group flex items-center px-2 py-1 text-sm rounded-md ${
                          pathname === child.href
                            ? 'text-primary-700 font-medium'
                            : 'text-gray-500 hover:text-gray-900'
                        }`}
                      >
                        {child.name}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
