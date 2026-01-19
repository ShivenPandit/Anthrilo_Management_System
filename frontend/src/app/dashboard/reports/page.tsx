'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import Link from 'next/link';

export default function ReportsPage() {
  const { data: summary, isLoading } = useQuery({
    queryKey: ['reportsSummary'],
    queryFn: async () => {
      const response = await apiClient.get('/reports/summary/all');
      return response.data;
    },
  });

  const reportCategories = [
    {
      title: 'Fabric Reports',
      icon: '🧵',
      color: 'blue',
      link: '/dashboard/reports/fabric',
      reports: [
        'Total Fabric Stock Sheet',
        'Type-wise Fabric Stock',
        'Period-based Fabric Stock',
        'Fabric Cost Sheet',
      ],
    },
    {
      title: 'Sales Reports',
      icon: '💰',
      color: 'green',
      link: '/dashboard/reports/sales',
      reports: [
        'Daily Sales Report',
        'SKU-wise Sales Analysis',
        'Panel-wise Sales Report',
        'Inactive Panels Report',
      ],
    },
    {
      title: 'Inventory Analysis',
      icon: '📦',
      color: 'yellow',
      link: '/dashboard/reports/inventory',
      reports: [
        'Slow Moving Inventory',
        'Fast Moving Inventory',
        'Reorder Recommendations',
      ],
    },
    {
      title: 'Production Reports',
      icon: '🏭',
      color: 'purple',
      link: '/dashboard/reports/production',
      reports: [
        'Production Plan Status',
        'Daily Production Variance',
        'Efficiency Analysis',
      ],
    },
  ];

  return (
    <div>
      <h1 className="mb-6">Reports & Analytics</h1>

      {/* Quick Summary Dashboard */}
      {isLoading ? (
        <div className="card mb-8 text-center py-12">
          <div className="text-gray-500">Loading summary...</div>
        </div>
      ) : summary ? (
        <div className="mb-8 space-y-6">
          {/* Overall Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Total Fabric Stock</div>
              <div className="text-3xl font-bold text-primary-600">
                {summary.fabric_summary?.total_fabrics || 0}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                ₹{(summary.fabric_summary?.total_value || 0).toFixed(2)}
              </div>
            </div>

            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Garment Inventory</div>
              <div className="text-3xl font-bold text-primary-600">
                {summary.inventory_summary?.total_items || 0}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {summary.inventory_summary?.total_stock || 0} units
              </div>
            </div>

            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Production Plans</div>
              <div className="text-3xl font-bold text-primary-600">
                {summary.production_summary?.total_plans || 0}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {summary.production_summary?.in_progress || 0} in progress
              </div>
            </div>

            <div className="card">
              <div className="text-sm text-gray-600 mb-1">Sales Panels</div>
              <div className="text-3xl font-bold text-primary-600">
                {summary.sales_summary?.total_panels || 0}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                {summary.sales_summary?.active_panels || 0} active
              </div>
            </div>
          </div>

          {/* Fabric Stock by Type */}
          {summary.fabric_summary?.by_type && (
            <div className="card">
              <h3 className="mb-4">Fabric Stock by Type</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.entries(summary.fabric_summary.by_type).map(([type, data]: [string, any]) => (
                  <div key={type} className="p-4 bg-gray-50 rounded-lg">
                    <div className="text-sm font-medium text-gray-600 mb-2">{type}</div>
                    <div className="text-2xl font-bold text-primary-600 mb-1">
                      {data.quantity.toFixed(2)} kg
                    </div>
                    <div className="text-sm text-gray-500">₹{data.value.toFixed(2)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Inventory Alerts */}
          {(summary.inventory_summary?.slow_moving_count > 0 ||
            summary.inventory_summary?.fast_moving_count > 0) && (
            <div className="card">
              <h3 className="mb-4">Inventory Alerts</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {summary.inventory_summary?.slow_moving_count > 0 && (
                  <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-2xl">🐌</span>
                      <span className="font-semibold text-yellow-800">Slow Moving Items</span>
                    </div>
                    <div className="text-3xl font-bold text-yellow-600 mb-1">
                      {summary.inventory_summary.slow_moving_count}
                    </div>
                    <Link
                      href="/dashboard/reports/inventory"
                      className="text-sm text-yellow-700 hover:underline"
                    >
                      View details →
                    </Link>
                  </div>
                )}

                {summary.inventory_summary?.fast_moving_count > 0 && (
                  <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-2xl">🚀</span>
                      <span className="font-semibold text-green-800">Fast Moving Items</span>
                    </div>
                    <div className="text-3xl font-bold text-green-600 mb-1">
                      {summary.inventory_summary.fast_moving_count}
                    </div>
                    <Link
                      href="/dashboard/reports/inventory"
                      className="text-sm text-green-700 hover:underline"
                    >
                      View details →
                    </Link>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* Report Categories */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {reportCategories.map((category) => (
          <Link key={category.title} href={category.link}>
            <div className="card hover:shadow-lg transition-shadow cursor-pointer h-full">
              <div className="flex items-start gap-4">
                <div className="text-5xl">{category.icon}</div>
                <div className="flex-1">
                  <h3 className="mb-2">{category.title}</h3>
                  <ul className="space-y-1">
                    {category.reports.map((report) => (
                      <li key={report} className="text-sm text-gray-600 flex items-center gap-2">
                        <span className="text-primary-500">•</span>
                        {report}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 text-sm text-primary-600 font-medium">
                    View reports →
                  </div>
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Export Options */}
      <div className="card mt-8">
        <h3 className="mb-4">Export & Download</h3>
        <p className="text-gray-600 mb-4">
          Generate and download comprehensive reports in various formats
        </p>
        <div className="flex gap-4">
          <button className="btn btn-secondary">📄 Export to Excel</button>
          <button className="btn btn-secondary">📊 Generate PDF</button>
          <button className="btn btn-secondary">📧 Email Reports</button>
        </div>
      </div>
    </div>
  );
}
