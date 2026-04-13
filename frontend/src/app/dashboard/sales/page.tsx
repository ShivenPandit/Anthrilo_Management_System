'use client';

import { useQuery } from '@tanstack/react-query';
import { ucSales } from '@/features/sales/api';
import Link from 'next/link';

export default function SalesPage() {
  const { data: todayData, isLoading } = useQuery({
    queryKey: ['unicommerce-today'],
    queryFn: async () => {
      const response = await ucSales.getToday();
      return response.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  const todayOrders = todayData?.summary?.total_orders || 0;
  const todayRevenue = todayData?.summary?.total_revenue || 0;
  const todayItems = todayData?.summary?.total_items || 0;
  const avgOrderValue = todayOrders > 0 ? todayRevenue / todayOrders : 0;

  const modules = [
    {
      title: 'Anthrilo Orders',
      description: 'View real-time orders from all channels',
      href: '/dashboard/garments/production',
      icon: '🛒',
      gradient: 'from-green-500 to-green-600',
      iconBg: 'bg-green-100 dark:bg-green-900/30',
      stats: `${todayOrders} orders today`,
    },
    {
      title: 'Channel Revenue',
      description: 'Marketplace-wise revenue breakdown',
      href: '/dashboard/reports/panels/settlement',
      icon: '🏪',
      gradient: 'from-purple-500 to-purple-600',
      iconBg: 'bg-purple-100 dark:bg-purple-900/30',
      stats: 'Track channel performance',
    },
    {
      title: 'Sales Reports',
      description: 'Detailed sales analytics & SKU breakdown',
      href: '/dashboard/reports/sales',
      icon: '📊',
      gradient: 'from-blue-500 to-blue-600',
      iconBg: 'bg-blue-100 dark:bg-blue-900/30',
      stats: 'Multiple report types',
    },
  ];

  return (
    <div className="page-section-gap">
      <div>
        <h1 className="responsive-title text-gray-900 dark:text-gray-100 mb-1.5 sm:mb-2">Sales Management</h1>
        <p className="responsive-subtitle text-gray-600 dark:text-gray-400">Real-time sales data from Anthrilo</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6">
        <div className="card bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-l-4 border-green-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-green-600 dark:text-green-400 mb-1">Today&apos;s Orders</p>
              <p className="text-2xl sm:text-3xl 2xl:text-4xl font-bold text-gray-900 dark:text-gray-100">{isLoading ? '...' : todayOrders}</p>
            </div>
            <div className="h-12 w-12 sm:h-14 sm:w-14 2xl:h-16 2xl:w-16 rounded-full bg-green-500/20 flex items-center justify-center"><span className="text-2xl sm:text-3xl 2xl:text-4xl">📦</span></div>
          </div>
        </div>

        <div className="card bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border-l-4 border-blue-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600 dark:text-blue-400 mb-1">Today&apos;s Revenue</p>
              <p className="text-xl sm:text-2xl 2xl:text-3xl font-bold text-gray-900 dark:text-gray-100">{isLoading ? '...' : `₹${todayRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`}</p>
            </div>
            <div className="h-12 w-12 sm:h-14 sm:w-14 2xl:h-16 2xl:w-16 rounded-full bg-blue-500/20 flex items-center justify-center"><span className="text-2xl sm:text-3xl 2xl:text-4xl">💰</span></div>
          </div>
        </div>

        <div className="card bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/20 border-l-4 border-emerald-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400 mb-1">Items Sold</p>
              <p className="text-2xl sm:text-3xl 2xl:text-4xl font-bold text-gray-900 dark:text-gray-100">{isLoading ? '...' : todayItems}</p>
            </div>
            <div className="h-12 w-12 sm:h-14 sm:w-14 2xl:h-16 2xl:w-16 rounded-full bg-emerald-500/20 flex items-center justify-center"><span className="text-2xl sm:text-3xl 2xl:text-4xl">📈</span></div>
          </div>
        </div>

        <div className="card bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-800/20 border-l-4 border-purple-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-purple-600 dark:text-purple-400 mb-1">Avg Order Value</p>
              <p className="text-xl sm:text-2xl 2xl:text-3xl font-bold text-gray-900 dark:text-gray-100">{isLoading ? '...' : `₹${avgOrderValue.toFixed(0)}`}</p>
            </div>
            <div className="h-12 w-12 sm:h-14 sm:w-14 2xl:h-16 2xl:w-16 rounded-full bg-purple-500/20 flex items-center justify-center"><span className="text-2xl sm:text-3xl 2xl:text-4xl">💵</span></div>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-xl sm:text-2xl 2xl:text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4 sm:mb-6">Sales Modules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4 sm:gap-6">
          {modules.map((module) => (
            <Link key={module.title} href={module.href}
              className="group relative card hover:shadow-2xl transition-all duration-300 overflow-hidden h-full">
              <div className={`absolute inset-0 bg-gradient-to-br ${module.gradient} opacity-0 group-hover:opacity-5 dark:group-hover:opacity-10 transition-opacity duration-300`}></div>
              <div className="relative">
                <div className="flex items-start justify-between mb-3 sm:mb-4">
                  <div className={`h-14 w-14 sm:h-16 sm:w-16 2xl:h-[4.5rem] 2xl:w-[4.5rem] rounded-2xl ${module.iconBg} flex items-center justify-center transform group-hover:scale-110 transition-all duration-300`}>
                    <span className="text-3xl sm:text-4xl">{module.icon}</span>
                  </div>
                </div>
                <h3 className="text-base sm:text-lg 2xl:text-xl font-semibold text-gray-900 dark:text-gray-100 mb-1.5 sm:mb-2">{module.title}</h3>
                <p className="text-sm 2xl:text-base text-gray-600 dark:text-gray-400 mb-2.5 sm:mb-3">{module.description}</p>
                <div className="flex items-center text-xs text-gray-500">
                  <span className="inline-block w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                  {module.stats}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
