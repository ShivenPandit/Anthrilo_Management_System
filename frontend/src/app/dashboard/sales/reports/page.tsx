'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function SalesReportsPage() {
  const salesReports = [
    {
      title: 'Sales Analytics',
      description: 'Comprehensive sales performance analysis',
      href: '/dashboard/reports/sales',
      icon: '📊',
    },
    {
      title: 'Bundle SKU Sales',
      description: 'Size-wise bundle sales breakdown',
      href: '/dashboard/reports/sales/bundle-sku',
      icon: '📦',
    },
    {
      title: 'General Discount Report',
      description: 'Product-wise discount analysis',
      href: '/dashboard/reports/sales/discount-general',
      icon: '🏷️',
    },
    {
      title: 'Discount by Panel',
      description: 'Panel-wise discount tracking',
      href: '/dashboard/reports/sales/discount-by-panel',
      icon: '🏪',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Sales Reports"
        description="Access comprehensive sales analytics and reports"
      />
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {salesReports.map((report) => (
          <Link
            key={report.title}
            href={report.href}
            className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 cursor-pointer border-l-4 border-l-primary-500"
          >
            <div className="flex items-start">
              <span className="text-4xl mr-4">{report.icon}</span>
              <div>
                <h3 className="mb-2 text-gray-900 dark:text-gray-100 font-semibold">{report.title}</h3>
                <p className="text-gray-600 dark:text-gray-400 text-sm">{report.description}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
