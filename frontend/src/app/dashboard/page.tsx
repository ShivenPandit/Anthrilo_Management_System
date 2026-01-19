'use client';

import { useQuery } from '@tanstack/react-query';
import { garmentApi } from '@/lib/api';
import { StatCard, PageHeader } from '@/components/ui/Common';
import Link from 'next/link';

export default function DashboardPage() {
  // Fetch summary data
  const { data: garments } = useQuery({
    queryKey: ['garments'],
    queryFn: async () => {
      const response = await garmentApi.getAll({ is_active: true });
      return response.data;
    },
  });

  const stats = [
    {
      title: 'Active Garments',
      value: garments?.length || 0,
      icon: '👕',
      color: 'blue' as const,
    },
    {
      title: 'Low Stock Items',
      value: 0,
      icon: '⚠️',
      color: 'yellow' as const,
    },
    {
      title: "Today's Sales",
      value: '0',
      icon: '💰',
      color: 'green' as const,
    },
    {
      title: 'Active Panels',
      value: '0',
      icon: '🏪',
      color: 'purple' as const,
    },
  ];

  const quickActions = [
    {
      title: 'View All Reports',
      description: 'Access all 19 business reports',
      href: '/dashboard/reports/reports-index',
      icon: '📊',
      color: 'blue',
    },
    {
      title: 'Purchase Raise',
      description: 'Check yarn purchase recommendations',
      href: '/dashboard/reports/raw-materials/purchase-raise',
      icon: '📦',
      color: 'red',
      badge: 'NEW',
    },
    {
      title: 'Panel Settlement',
      description: 'Calculate panel settlements',
      href: '/dashboard/reports/panels/settlement',
      icon: '💵',
      color: 'green',
      badge: 'NEW',
    },
    {
      title: 'Bundle Sales',
      description: 'Size-wise sales analysis',
      href: '/dashboard/reports/sales/bundle-sku',
      icon: '📈',
      color: 'yellow',
      badge: 'NEW',
    },
    {
      title: 'Discount Analysis',
      description: 'Product discount reports',
      href: '/dashboard/reports/sales/discount-general',
      icon: '🏷️',
      color: 'purple',
      badge: 'NEW',
    },
    {
      title: 'Add Garment',
      description: 'Create new garment product',
      href: '/dashboard/garments/master',
      icon: '➕',
      color: 'indigo',
    },
  ];

  return (
    <div>
      <PageHeader
        title="Dashboard Overview"
        description="Welcome to Anthrilo Management System"
      />

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat) => (
          <StatCard
            key={stat.title}
            title={stat.title}
            value={stat.value}
            icon={stat.icon}
            color={stat.color}
          />
        ))}
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-xl font-bold mb-4 text-gray-900 dark:text-gray-100">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {quickActions.map((action) => (
            <Link
              key={action.title}
              href={action.href}
              className="card hover:shadow-2xl hover:scale-105 transition-all duration-300 cursor-pointer group border-l-4 border-l-primary-500 dark:border-l-primary-400"
            >
              <div className="flex items-start justify-between mb-3">
                <span className="text-4xl">{action.icon}</span>
                {action.badge && (
                  <span className="px-3 py-1 bg-gradient-to-r from-green-400 to-green-500 text-white dark:from-green-500 dark:to-green-600 text-xs rounded-full font-bold shadow-md animate-pulse">
                    {action.badge}
                  </span>
                )}
              </div>
              <h3 className="mb-2 text-gray-900 dark:text-gray-100 font-semibold group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                {action.title}
              </h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">{action.description}</p>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="card">
        <h2 className="mb-4 text-gray-900 dark:text-gray-100">Getting Started</h2>
        <div className="space-y-4">
          <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
            <div className="flex items-start">
              <span className="text-2xl mr-3">✅</span>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">System Setup Complete</p>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Database configured and all 19 reports are ready to use
                </p>
              </div>
            </div>
          </div>
          <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
            <div className="flex items-start">
              <span className="text-2xl mr-3">📝</span>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">Next Steps</p>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  1. Add garment products • 2. Create sales records • 3. Generate reports
                </p>
              </div>
            </div>
          </div>
          <div>
            <div className="flex items-start">
              <span className="text-2xl mr-3">🎯</span>
              <div>
                <p className="font-medium text-gray-900 dark:text-gray-100">Explore Reports</p>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Navigate to Reports section to explore stock analysis, forecasting,
                  discounts, and settlement reports
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
