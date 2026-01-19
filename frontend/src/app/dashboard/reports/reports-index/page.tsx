'use client';

import Link from 'next/link';
import { PageHeader } from '@/components/ui/Common';

const reportCategories = [
  {
    category: 'Raw Materials & Processing',
    icon: '📦',
    color: 'blue',
    reports: [
      {
        title: 'Stock Analysis',
        description: 'Monitor inventory levels and stock status',
        href: '/dashboard/reports/raw-materials/stock-analysis',
      },
      {
        title: 'Yarn Forecasting',
        description: 'AI-powered demand forecasting for yarn',
        href: '/dashboard/reports/raw-materials/yarn-forecasting',
      },
      {
        title: 'Purchase Raise for Yarn',
        description: 'Automated purchase recommendations',
        href: '/dashboard/reports/raw-materials/purchase-raise',
        badge: 'NEW',
      },
    ],
  },
  {
    category: 'Production & Quality',
    icon: '🏭',
    color: 'green',
    reports: [
      {
        title: 'Production Tracking',
        description: 'Track garment production progress',
        href: '/dashboard/reports/production',
      },
      {
        title: 'Quality Metrics',
        description: 'Quality control analysis',
        href: '/dashboard/reports/production',
      },
    ],
  },
  {
    category: 'Sales & Discounts',
    icon: '💰',
    color: 'yellow',
    reports: [
      {
        title: 'Sales Analytics',
        description: 'Comprehensive sales performance analysis',
        href: '/dashboard/reports/sales',
      },
      {
        title: 'Bundle SKU Sales',
        description: 'Size-wise bundle sales breakdown',
        href: '/dashboard/reports/sales/bundle-sku',
        badge: 'NEW',
      },
      {
        title: 'General Discount Report',
        description: 'Product-wise discount analysis',
        href: '/dashboard/reports/sales/discount-general',
        badge: 'NEW',
      },
      {
        title: 'Discount by Panel',
        description: 'Panel-wise discount tracking',
        href: '/dashboard/reports/sales/discount-by-panel',
        badge: 'NEW',
      },
    ],
  },
  {
    category: 'Panel Management',
    icon: '🏪',
    color: 'purple',
    reports: [
      {
        title: 'Panel Performance',
        description: 'Track panel sales performance',
        href: '/dashboard/reports/panels',
      },
      {
        title: 'Top Performing Panels',
        description: 'Identify best performing panels',
        href: '/dashboard/reports/panels',
      },
      {
        title: 'Panel Settlement',
        description: 'Calculate settlements with commissions',
        href: '/dashboard/reports/panels/settlement',
        badge: 'NEW',
      },
    ],
  },
  {
    category: 'Labour & HR',
    icon: '👥',
    color: 'red',
    reports: [
      {
        title: 'Attendance Report',
        description: 'Track employee attendance',
        href: '/dashboard/reports/labour',
      },
      {
        title: 'Productivity Analysis',
        description: 'Measure labour productivity',
        href: '/dashboard/reports/labour',
      },
      {
        title: 'Labour Cost Report',
        description: 'Analyze labour costs',
        href: '/dashboard/reports/labour',
      },
    ],
  },
  {
    category: 'Financial Reports',
    icon: '📊',
    color: 'indigo',
    reports: [
      {
        title: 'Purchase Analysis',
        description: 'Raw material purchase tracking',
        href: '/dashboard/reports/financial',
      },
      {
        title: 'Sales Analysis',
        description: 'Finished goods sales performance',
        href: '/dashboard/reports/financial',
      },
      {
        title: 'Profit Margin',
        description: 'Profitability analysis',
        href: '/dashboard/reports/financial',
      },
      {
        title: 'Expense Tracking',
        description: 'Track all business expenses',
        href: '/dashboard/reports/financial',
      },
    ],
  },
];

export default function ReportsPage() {
  return (
    <div>
      <PageHeader
        title="Reports & Analytics"
        description="Access comprehensive business intelligence and reporting tools (19 reports available)"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {reportCategories.map((category) => (
          <div key={category.category} className="card">
            <div className="flex items-center mb-4">
              <span className="text-3xl mr-3">{category.icon}</span>
              <h2 className="text-xl font-bold">{category.category}</h2>
            </div>
            <div className="space-y-3">
              {category.reports.map((report) => (
                <Link
                  key={report.title}
                  href={report.href}
                  className="block p-4 border border-gray-200 rounded-lg hover:border-primary-500 hover:shadow-md transition-all"
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-semibold text-gray-900 mb-1">
                        {report.title}
                        {report.badge && (
                          <span className="ml-2 px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-bold">
                            {report.badge}
                          </span>
                        )}
                      </h3>
                      <p className="text-sm text-gray-600">{report.description}</p>
                    </div>
                    <svg
                      className="w-5 h-5 text-gray-400"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
