'use client';

import { PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function RawMaterialsPage() {
  const modules = [
    {
      title: 'Yarn Management',
      description: 'Manage yarn inventory, types, and procurement',
      icon: '🧶',
      href: '/dashboard/raw-materials/yarn',
      color: 'blue',
    },
    {
      title: 'Fabric Management',
      description: 'Track fabric stock, types, and GSM specifications',
      icon: '🧵',
      href: '/dashboard/raw-materials/fabric',
      color: 'green',
    },
    {
      title: 'Process Management',
      description: 'Manage knitting, dyeing, finishing, and printing processes',
      icon: '⚙️',
      href: '/dashboard/raw-materials/processes',
      color: 'purple',
    },
  ];

  const reports = [
    {
      title: 'Stock Analysis',
      description: 'Real-time inventory tracking and stock levels',
      icon: '📊',
      href: '/dashboard/reports/raw-materials/stock-analysis',
    },
    {
      title: 'Yarn Forecasting',
      description: 'AI-powered demand prediction for yarn',
      icon: '🔮',
      href: '/dashboard/reports/raw-materials/yarn-forecasting',
    },
    {
      title: 'Purchase Raise',
      description: 'Automated procurement recommendations',
      icon: '🛒',
      href: '/dashboard/reports/raw-materials/purchase-raise',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Raw Materials & Processing"
        description="Manage yarn, fabric, and processing operations"
      />

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Yarn Types</p>
          <p className="text-3xl font-bold text-blue-600 dark:text-blue-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Total Fabrics</p>
          <p className="text-3xl font-bold text-green-600 dark:text-green-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Active Processes</p>
          <p className="text-3xl font-bold text-purple-600 dark:text-purple-400 mt-2">0</p>
        </div>
        <div className="card hover:shadow-xl transition-shadow">
          <p className="text-sm text-gray-600 dark:text-gray-400">Stock Value</p>
          <p className="text-3xl font-bold text-orange-600 dark:text-orange-400 mt-2">₹0</p>
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
              className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 border-l-4 border-l-blue-500 dark:border-l-blue-400"
            >
              <div className="text-4xl mb-3">{module.icon}</div>
              <h3 className="mb-2 text-gray-900 dark:text-gray-100">{module.title}</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">{module.description}</p>
              <div className="mt-4 text-primary-600 dark:text-primary-400 text-sm font-medium">
                Manage →
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
