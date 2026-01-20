'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function FinancialPage() {
  const modules = [
    {
      title: 'Discount Management',
      description: 'Track and manage product discounts',
      icon: '💸',
      href: '/dashboard/financial/discounts',
      color: 'blue',
    },
    {
      title: 'Paid Ads',
      description: 'Track advertising spend and performance',
      icon: '📢',
      href: '/dashboard/financial/ads',
      color: 'green',
    },
    {
      title: 'ROI Analysis',
      description: 'Return on investment analytics',
      icon: '📊',
      href: '/dashboard/financial/roi',
      color: 'purple',
    },
  ];

  const reports = [
    {
      title: 'Discount Reports',
      description: 'General & panel-wise discount analysis',
      icon: '💰',
      href: '/dashboard/reports/sales/discount-general',
    },
    {
      title: 'Panel Settlement',
      description: 'Commission & logistics calculations',
      icon: '🧾',
      href: '/dashboard/reports/panels/settlement',
    },
    {
      title: 'Profit Margins',
      description: 'Product-wise profitability analysis',
      icon: '📈',
      href: '/dashboard/financial/roi',
    },
  ];

  const metrics = [
    {
      title: 'Total Revenue',
      value: '₹0',
      change: '+0%',
      icon: '💵',
      positive: true,
    },
    {
      title: 'Ad Spend',
      value: '₹0',
      change: '+0%',
      icon: '📢',
      positive: false,
    },
    {
      title: 'Net Profit',
      value: '₹0',
      change: '+0%',
      icon: '💰',
      positive: true,
    },
    {
      title: 'ROI',
      value: '0%',
      change: '+0%',
      icon: '📊',
      positive: true,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Financial Management"
        description="Track finances, manage discounts, and analyze profitability"
      />

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        {metrics.map((metric, index) => (
          <div
            key={metric.title}
            className={`card hover:shadow-xl transition-shadow bg-gradient-to-br ${
              index === 0
                ? 'from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20'
                : index === 1
                ? 'from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20'
                : index === 2
                ? 'from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20'
                : 'from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20'
            }`}
          >
            <div className="flex justify-between items-start mb-2">
              <p className="text-sm text-gray-600 dark:text-gray-400">{metric.title}</p>
              <span className="text-2xl">{metric.icon}</span>
            </div>
            <p
              className={`text-3xl font-bold mt-2 ${
                index === 0
                  ? 'text-green-600 dark:text-green-400'
                  : index === 1
                  ? 'text-red-600 dark:text-red-400'
                  : index === 2
                  ? 'text-blue-600 dark:text-blue-400'
                  : 'text-purple-600 dark:text-purple-400'
              }`}
            >
              {metric.value}
            </p>
            <p
              className={`text-xs mt-1 ${
                metric.positive
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              {metric.positive ? '↑' : '↓'} {metric.change} this month
            </p>
          </div>
        ))}
      </div>

      {/* Financial Insights Card */}
      <div className="card mb-8 bg-gradient-to-r from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 border-l-4 border-l-purple-500">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              💡 Financial Insights
            </h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">
              Get comprehensive insights into your business finances, profitability, and growth metrics
            </p>
            <div className="flex gap-3">
              <Link href="/dashboard/financial/roi" className="btn btn-primary">
                View Analytics
              </Link>
              <Link
                href="/dashboard/reports/panels/settlement"
                className="btn btn-secondary"
              >
                Settlement Reports
              </Link>
            </div>
          </div>
          <div className="text-6xl opacity-20">💎</div>
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
              className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-purple-500 dark:border-l-purple-400"
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
              className="card hover:shadow-xl transition-all group"
            >
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
