'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function SalesPage() {
  const modules = [
    {
      title: 'Sales Transactions',
      description: 'Record and manage daily sales transactions',
      icon: '💰',
      href: '/dashboard/sales/transactions',
      color: 'blue',
    },
    {
      title: 'Panel Management',
      description: 'Manage sales panels and channels',
      icon: '🏪',
      href: '/dashboard/sales/panels',
      color: 'green',
    },
    {
      title: 'Sales Reports',
      description: 'View detailed sales analytics and reports',
      icon: '📊',
      href: '/dashboard/sales/reports',
      color: 'purple',
    },
  ];

  const reports = [
    {
      title: 'Daily Sales',
      description: 'View today\'s sales performance',
      icon: '📅',
      href: '/dashboard/reports/sales',
      badge: 'Live',
    },
    {
      title: 'Bundle SKU Sales',
      description: 'Size-wise sales breakdown',
      icon: '📦',
      href: '/dashboard/reports/sales/bundle-sku',
    },
    {
      title: 'Discount Reports',
      description: 'General & panel-wise discount analysis',
      icon: '💸',
      href: '/dashboard/reports/sales/discount-general',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Sales Management"
        description="Track sales, manage panels, and analyze performance"
      />

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Today's Sales</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">₹0</p>
          <p className="text-xs text-green-600 dark:text-green-400 mt-1">↑ 0% from yesterday</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Transactions</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Today</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Active Panels</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">0</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Channels</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-800/20">
          <p className="text-sm text-gray-600 dark:text-gray-400">Avg Discount</p>
          <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">0%</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">This Month</p>
        </div>
      </div>

      {/* Sales Overview Card */}
      <div className="card mb-8 bg-gradient-to-r from-primary-50 to-blue-50 dark:from-primary-900/20 dark:to-blue-900/20 border-l-4 border-l-primary-500">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              📈 Performance Overview
            </h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">
              Track your sales performance across all channels and analyze trends
            </p>
            <Link
              href="/dashboard/reports/sales"
              className="btn btn-primary inline-block"
            >
              View Detailed Reports
            </Link>
          </div>
          <div className="text-6xl opacity-20">💰</div>
        </div>
      </div>

      {/* Management Modules */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Management</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {modules.map((module) => (
            <Link
              key={module.href}
              href={module.href}
              className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-green-500 dark:border-l-green-400"
            >
              <div className="text-4xl mb-3">{module.icon}</div>
              <h3 className="mb-2 text-gray-900 dark:text-gray-100 font-semibold">{module.title}</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">{module.description}</p>
              <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-medium">
                Open Module →
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Reports */}
      <div>
        <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Reports & Analytics</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {reports.map((report) => (
            <Link
              key={report.href}
              href={report.href}
              className="card hover:shadow-xl transition-all group relative"
            >
              {report.badge && (
                <span className="absolute top-4 right-4 px-2 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 text-xs font-semibold rounded-full">
                  {report.badge}
                </span>
              )}
              <div className="text-3xl mb-3 group-hover:scale-110 transition-transform">
                {report.icon}
              </div>
              <h3 className="mb-2 text-gray-900 dark:text-gray-100 font-semibold">{report.title}</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">{report.description}</p>
              <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-medium">
                View Report →
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
